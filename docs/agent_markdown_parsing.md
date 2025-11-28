## Agent Markdown 输出解析通用规范

本规范总结了 `PaperOverviewAgent` / `RequirementChecklistAgent` / `LaTeXPaperGeneratorAgent` 等现有 Agent 的解析方式，作为后续新 Agent 复用的模板。

目标：**统一一套「大模型 → Markdown 代码块 → 解析成文件」的模式**，只改业务 Prompt 和内容结构，不改解析骨架。

---

## 1. 整体设计思路

- **输出约定在 SYSTEM_PROMPT 中写死**：
  - Agent 不能直接写文件，只能输出特定 markdown 结构。
  - 必须包含：
    - 一个 ` ```path` 代码块：写文件名。
    - 一个内容代码块：如 ` ```text` / ` ```markdown` / ` ```latex` 等。
- **后端解析职责**：
  - 使用正则从大模型原始字符串中提取：
    - `file_name`：`path` 代码块内容。
    - `file_content`：内容代码块内容。
    - （可选）额外状态，如 `is_skipped` / `skip_reason` 等。
- **重试策略**：
  - 如果解析失败（匹配不到代码块或内容为空），返回 `None`。
  - 用 `tenacity.AsyncRetrying(retry_if_result(...))` 自动重试若干次。
  - 重试时在 user prompt 中**加强格式约束提示**，并适度降低 `temperature`。

---

## 2. 输出格式统一约定

### 2.1 固定结构

每个 Agent 的 SYSTEM_PROMPT 中，都应明确写出如下结构（根据业务调整内容块 tag）：

```text
```path
[FILE_NAME]
```

```<CONTENT_TAG>
[FILE_CONTENT]
```
```

- **`path` 代码块**：
  - 只放文件名，例如：
    - `Deep_Learning_Method_paper_overview.txt`
    - `requirements_checklist.md`
    - `paper_framework.tex`
- **内容代码块**：
  - 标签由 Agent 决定，例如：
    - 概览：`text`
    - 清单：`markdown`
    - LaTeX：`latex`
  - 内容为该文件的完整文本。

### 2.2 强制性约束（必须写进 SYSTEM_PROMPT）

建议在 SYSTEM_PROMPT 里添加类似的硬性规则（不同 Agent 文案可复用）：

- **格式硬约束**：
  - Must output **exactly two code blocks**:
    - One ` ```path` block with the file name.
    - One ` ```<CONTENT_TAG>` block with the file content.
  - **Do NOT output any explanations, comments, or questions outside these code blocks.**
- **解析说明**：
  - The orchestrator will parse this markdown and save the file.
  - You cannot perform any file operations directly.

这样可以最大程度减少大模型输出跑偏、无法解析的问题。

---

## 3. 正则解析模板

### 3.1 基础通用正则

统一使用「宽松但安全」的匹配规则，支持以下两种写法：

- 多行：

```text
```path
file_name.ext
```
```

- 同行：

```text
```path file_name.ext ```
```

推荐的正则模板（Python）：

```python
import re

def parse_markdown_blocks(
    response: str,
    content_tag: str,
) -> tuple[str | None, str | None]:
    """
    通用解析：从 markdown 响应中提取 `path` 和指定内容块。

    Args:
        response: 大模型原始字符串响应
        content_tag: 内容代码块标签，如 'text' / 'markdown' / 'latex'

    Returns:
        (file_name, file_content) 任一失败则返回 (None, None)
    """
    if not response:
        return None, None

    # path block
    path_pattern = r'```path\s*\n?(.*?)\n?```'
    path_match = re.search(path_pattern, response, re.DOTALL)

    if not path_match:
        return None, None

    # content block
    content_pattern = rf'```{re.escape(content_tag)}\s*\n?(.*?)\n?```'
    content_match = re.search(content_pattern, response, re.DOTALL)

    if not content_match:
        return None, None

    file_name = path_match.group(1).strip()
    file_content = content_match.group(1).strip()

    return file_name, file_content
```

> 现有实现中分别写成了：
> - `text_pattern = r'```text\s*\n?(.*?)\n?```'`
> - `markdown_pattern = r'```markdown\s*\n?(.*?)\n?```'`
> - `latex_pattern = r'```latex\s*\n?(.*?)\n?```'`
>
> 上面的 `parse_markdown_blocks` 是将这三种情况抽象成一个通用函数。

### 3.2 带 SKIP 状态的解析（可选）

对于像 `LaTeXPaperGeneratorAgent` 这种既可能生成文件、又可能「跳过」的 Agent，可以加入一个 `is_skipped` 逻辑：

```python
def parse_markdown_with_skip(
    response: str,
    content_tag: str,
    skip_keywords: tuple[str, ...] = ("SKIPPED", "SKIP"),
) -> tuple[str | None, str | None, bool]:
    """
    带 SKIP 状态的通用解析。

    Returns:
        (file_name, file_content, is_skipped)
    """
    if not response:
        return None, None, False

    upper = response.upper()
    if any(kw in upper for kw in skip_keywords):
        # 认为是 SKIP，file_name/file_content 交给上层决定是否需要
        return None, response, True

    file_name, file_content = parse_markdown_blocks(response, content_tag)
    return file_name, file_content, False
```

- 上层可以根据 `is_skipped` 决定：
  - 不重试；
  - 直接返回 `{"is_skipped": True, "skip_reason": ...}` 一类结构。

---

## 4. 生成 + 解析 + 重试 模式模板

下面是抽象后的「一次生成尝试 + 重试框架」模式，适用于大部分 Agent。

### 4.1 单次生成尝试（内部方法）

```python
from tenacity import AsyncRetrying, retry_if_result, stop_after_attempt, wait_exponential
from app.utils.logger import logger


async def _generate_attempt(
    openai_service,
    system_prompt: str,
    user_content: str,
    content_tag: str,
    temperature: float | None,
    max_tokens: int,
    model: str | None,
    attempt_number: int = 1,
) -> dict | None:
    # 默认 temperature
    if temperature is None:
        temperature = 0.7

    # 重试时降低 temperature 提高稳定性
    adjusted_temperature = max(0.3, temperature - (attempt_number - 1) * 0.1)

    # 构造 user 消息，重试时加强格式提示
    if attempt_number > 1:
        user_content += (
            "\n\n⚠️ IMPORTANT: You MUST output in the exact format with "
            "```path and ```" + content_tag +
            " blocks. Ensure both blocks are present and properly formatted. "
            "Do NOT output explanations or questions outside the markdown blocks."
        )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]

    logger.info(f"Attempt {attempt_number}: generating via {model}")

    raw_response, usage = await openai_service.chat_completion(
        messages=messages,
        temperature=adjusted_temperature,
        max_tokens=max_tokens,
        model=model,
    )

    file_name, file_content = parse_markdown_blocks(raw_response, content_tag)
    if file_name is None or file_content is None:
        logger.warning(f"Attempt {attempt_number}: parse failed")
        return None

    return {
        "file_name": file_name,
        "file_content": file_content,
        "raw_response": raw_response,
        "usage": usage,
    }
```

### 4.2 带重试的对外方法

```python
async def generate_with_retry(
    *,
    openai_service,
    system_prompt: str,
    user_content: str,
    content_tag: str,
    temperature: float | None = 0.7,
    max_tokens: int = 4000,
    model: str | None = None,
    max_attempts: int = 3,
) -> dict:
    def is_parse_failed(result: dict | None) -> bool:
        return result is None

    last_result: dict | None = None
    total_attempts = 0

    try:
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(max_attempts),
            retry=retry_if_result(is_parse_failed),
            wait=wait_exponential(multiplier=1, min=2, max=10),
        ):
            with attempt:
                attempt_number = attempt.retry_state.attempt_number
                total_attempts = attempt_number

                last_result = await _generate_attempt(
                    openai_service=openai_service,
                    system_prompt=system_prompt,
                    user_content=user_content,
                    content_tag=content_tag,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    model=model,
                    attempt_number=attempt_number,
                )

                if last_result is None:
                    continue

                return last_result
    except Exception as e:
        logger.error(
            f"Failed after {total_attempts} attempts. "
            f"Expected markdown with ```path and ```{content_tag} blocks."
        )
        raise

    # 理论上不会走到这里，如果走到这里说明重试逻辑出了问题
    if last_result is None:
        raise ValueError(
            f"Agent output format is invalid. "
            f"Expected markdown with ```path and ```{content_tag} blocks."
        )
    return last_result
```

> 实际项目中，每个 Agent 可以在此基础上增加自己的入参（如 `user_document` / `paper_overview` / `latex_content` 等），但整个「生成 + 解析 + 重试」骨架保持不变。

---

## 5. 新 Agent 接入 Checklist

新写一个 Agent 时，可以按下面 checklist 走一遍：

- **1）确定内容类型**
  - 目标文件扩展名：`.txt` / `.md` / `.tex` / `.json` ...
  - 内容块标签：`text` / `markdown` / `latex` / `json` / `yaml` ...

- **2）在 SYSTEM_PROMPT 里写死输出格式**
  - 明确示例：
    - ` ```path` 块内是文件名。
    - ` ```<CONTENT_TAG>` 块内是完整内容。
  - 写清禁止事项：
    - 不得在代码块外输出解释 / 问题。
    - 不得省略任一代码块。

- **3）复用通用解析函数**
  - 使用 `parse_markdown_blocks(response, content_tag='<your_tag>')` 拿到 `(file_name, file_content)`。
  - 如需 SKIP 语义，使用 `parse_markdown_with_skip`。

- **4）接入重试框架**
  - 使用 `tenacity.AsyncRetrying + retry_if_result`：
    - 解析失败（返回 `None`）则重试。
    - 重试次数：一般 3 次足够，必要时可调。
  - 重试时：
    - 降低 `temperature`。
    - 在 user prompt 末尾添加更强硬的格式提示。

- **5）对外 API 返回统一结构**
  - 建议统一返回：
    - `file_name`
    - `file_content`
    - `raw_response`
    - `usage`
    - （可选）`is_skipped` / `skip_reason`

这样，后续再写新的 Agent，只需要关注：

- 业务逻辑 & Prompt 设计；
- 文件名和内容结构设计；

而「大模型输出 → markdown 解析 → 重试」这一整套机制可以完全复用。 


