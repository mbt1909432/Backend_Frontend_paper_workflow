# 重试机制说明

## 概述

重试机制用于处理 AI 模型输出格式解析失败的情况。当模型返回的内容不符合预期的 markdown 格式（缺少 ````path` 或 ````text` 代码块）时，系统会自动重试，最多尝试 3 次。

该机制使用 `tenacity` 库实现，采用智能参数调整和提示增强策略，以提高重试成功率。

## 重试条件

### 触发条件
- **解析失败**：`_parse_markdown_output` 方法返回 `(None, None)`
- **原因**：模型输出缺少必需的 markdown 代码块格式
  - 缺少 ````path` 代码块
  - 缺少 ````text` 代码块
  - 格式不正确或包含额外内容

### 不触发条件
- 解析成功，返回有效结果字典
- API 调用异常（网络错误、认证失败等）直接抛出，不进行重试

## 重试策略

### 1. 参数调整策略

#### Temperature 递减
每次重试时降低 temperature 参数，以提高输出的稳定性和格式一致性。

- **计算公式**：`adjusted_temperature = max(0.3, temperature - (attempt_number - 1) * 0.1)`
- **示例**（初始 temperature = 0.7）：
  - 第 1 次尝试：0.7（原始值）
  - 第 2 次尝试：0.6（降低 0.1）
  - 第 3 次尝试：0.5（降低 0.2）
- **最低限制**：0.3（确保输出不会过于死板）

**原理**：较低的 temperature 使模型输出更加确定性和结构化，有助于生成符合格式要求的内容。

### 2. 提示增强策略

在重试时，系统会在用户提示后追加格式要求警告：

```
⚠️ IMPORTANT: You MUST output in the exact format with ```path and ```text blocks. 
Ensure both blocks are present and properly formatted. 
Do NOT output explanations or questions outside the markdown blocks.
```

- **应用时机**：第 2 次和第 3 次重试
- **目的**：明确强调格式要求，减少模型输出不符合格式的情况

### 3. 等待策略（指数退避）

使用指数退避算法，避免频繁请求导致的问题：

- **配置**：`wait_exponential(multiplier=1, min=2, max=10)`
- **等待时间**：
  - 第 1 次失败后：等待 2 秒
  - 第 2 次失败后：等待约 4 秒（2 × 2）
  - 最大等待时间：10 秒

**优势**：
- 给 API 服务喘息时间
- 避免触发速率限制
- 提高重试成功率

## 完整流程

### 执行流程图

```
开始 generate_overview()
  ↓
尝试 1 (temperature = 0.7, 正常提示)
  ↓
调用 _generate_overview_attempt()
  ↓
调用 OpenAI API
  ↓
解析响应 _parse_markdown_output()
  ↓
┌─────────────────┬─────────────────┐
│   解析成功      │   解析失败       │
│  (返回结果)     │  (返回 None)     │
└────────┬────────┴────────┬────────┘
         │                 │
   返回结果字典            │
         │                 │
    ✅ 成功结束            │
                          │
                  等待 2 秒
                          ↓
         尝试 2 (temperature = 0.6, 增强提示)
                          ↓
         调用 _generate_overview_attempt()
                          ↓
         调用 OpenAI API
                          ↓
         解析响应
                          ↓
         ┌──────────────┬──────────────┐
         │  解析成功    │  解析失败     │
         │ (返回结果)   │ (返回 None)   │
         └──────┬───────┴──────┬───────┘
                │              │
          返回结果字典          │
                │              │
           ✅ 成功结束          │
                               │
                       等待 4 秒
                               ↓
              尝试 3 (temperature = 0.5, 增强提示)
                               ↓
              调用 _generate_overview_attempt()
                               ↓
              调用 OpenAI API
                               ↓
              解析响应
                               ↓
              ┌──────────────┬──────────────┐
              │  解析成功    │  解析失败     │
              │ (返回结果)   │ (返回 None)   │
              └──────┬───────┴──────┬───────┘
                     │              │
               返回结果字典          │
                     │              │
                ✅ 成功结束          │
                                    │
                            抛出 RetryError
                                    ↓
                            捕获并抛出 ValueError
                                    ↓
                            ❌ 失败结束
```

### 代码执行逻辑

1. **初始化重试器**：配置 `AsyncRetrying` 对象
2. **进入重试循环**：使用 `async for` 遍历重试尝试
3. **执行尝试**：调用 `_generate_overview_attempt`
4. **检查结果**：
   - 成功：立即返回结果，退出循环
   - 失败：继续下一次尝试
5. **处理最终失败**：捕获 `RetryError`，抛出详细的 `ValueError`

## 日志记录

### 日志级别和内容

- **INFO 级别**：
  - 每次尝试开始：`"Generating paper overview (attempt X/3)"`
  - 尝试成功：`"Paper overview generated successfully on attempt X"`
  - 单次尝试开始：`"Attempt X: Generating paper overview"`

- **DEBUG 级别**：
  - 输入文档长度和预览
  - 使用的参数（temperature, max_tokens, model）
  - 完整响应内容

- **WARNING 级别**：
  - 解析失败警告
  - 缺少代码块的具体信息
  - 重试前的警告（通过 `before_sleep_log`）

- **ERROR 级别**：
  - 所有重试都失败
  - 最后的结果和输入文档预览
  - 解析异常

### 调试信息

当解析失败时，系统会记录：
- 完整的原始响应内容
- 输入文档的前 200 个字符预览
- 使用的参数配置

## 错误处理

### 成功情况
- 任何一次尝试成功，立即返回结果字典：
  ```python
  {
      "file_name": str,
      "file_content": str,
      "raw_response": str,
      "usage": dict
  }
  ```

### 失败情况
- 所有 3 次尝试都失败后，抛出 `ValueError`，包含：
  - 尝试次数
  - 错误描述
  - 提示查看日志获取详细信息

## 关键特性总结

1. **智能重试**：只重试解析失败，不重试 API 异常
2. **参数优化**：重试时降低 temperature 提高稳定性
3. **提示增强**：重试时明确强调格式要求
4. **指数退避**：避免频繁请求和速率限制
5. **完整日志**：记录所有关键信息便于调试
6. **错误友好**：提供详细的错误信息帮助排查问题

## 使用建议

1. **监控日志**：关注 WARNING 和 ERROR 日志，了解重试频率
2. **调整参数**：如果重试频繁，考虑：
   - 降低初始 temperature
   - 增强系统提示（SYSTEM_PROMPT）
   - 检查输入文档质量
3. **优化提示**：确保系统提示明确要求输出格式
4. **错误处理**：在调用方捕获 `ValueError`，提供用户友好的错误提示

