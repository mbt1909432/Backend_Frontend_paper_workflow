# Methods Writing Agent

## 概述

`MethodsWritingAgent` 是一个专门用于撰写学术论文 Methods 部分的 Agent。它基于 `InnovationSynthesisAgent` 生成的 JSON 格式方法设计，生成结构化的 LaTeX Methods 章节，强调：

- 每个模块的动机和设计改进（基于 module_blueprints）
- 详细的实现细节和步骤（基于 method_pipeline）
- 模块间的连接和数据流（基于 integration_strategy）
- 训练和优化过程（基于 training_and_optimization）
- 数学公式化（从 JSON 中提取的数学规范）

## 使用方法

### 基本示例（与 InnovationSynthesisAgent 配合使用）

```python
from app.services.openai_service import OpenAIService
from app.core.agents.innovation_synthesis_agent import InnovationSynthesisAgent
from app.core.agents.writing.methods_writing_agent import MethodsWritingAgent

# 初始化服务
openai_service = OpenAIService()

# 步骤 1: 使用 InnovationSynthesisAgent 生成方法设计
innovation_agent = InnovationSynthesisAgent(openai_service=openai_service)
innovation_result = await innovation_agent.generate_innovation_plan(
    module_payload=module_payload,  # 包含三个模块的描述
    keywords=keywords
)

# 获取生成的 JSON
innovation_json = innovation_result["json"]

# 步骤 2: 使用 MethodsWritingAgent 生成 LaTeX Methods 部分
methods_agent = MethodsWritingAgent(openai_service=openai_service)
result = await methods_agent.generate_methods_section(
    innovation_json=innovation_json,
    temperature=0.7,
    max_tokens=12000
)

# 获取生成的 LaTeX 内容
latex_content = result["latex_content"]
print(latex_content)
```

### 从已保存的 JSON 文件加载

```python
import json
from pathlib import Path
from app.services.openai_service import OpenAIService
from app.core.agents.writing.methods_writing_agent import MethodsWritingAgent

# 加载之前保存的 innovation_synthesis.json
artifact_path = Path("path/to/innovation_synthesis.json")
with open(artifact_path, "r", encoding="utf-8") as f:
    artifact_data = json.load(f)

# 提取 JSON 输出
innovation_json = artifact_data["output"]

# 生成 Methods 部分
openai_service = OpenAIService()
methods_agent = MethodsWritingAgent(openai_service=openai_service)
result = await methods_agent.generate_methods_section(
    innovation_json=innovation_json
)

latex_content = result["latex_content"]
```

### 输出格式

Agent 返回一个字典，包含：

- `latex_content`: 生成的 LaTeX Methods 章节内容
- `raw_response`: 完整的原始响应
- `usage`: Token 使用统计

### 参数说明

- `innovation_json`: **必需**，`InnovationSynthesisAgent.generate_innovation_plan()` 返回的 `json` 字段
  - 可以传入完整的 JSON，Agent 会自动提取关键信息
  - 关键信息包括：
    - `final_problem_statement` (一句话问题陈述，用于 Methods 引言)
    - `final_method_proposal_text` (详细方法提案，包含实现步骤和具体细节)
    - `method_context` (仅 `research_question` 和 `problem_gap`)
    - `module_blueprints` (完整)
    - `integration_strategy.selected_pipeline` (仅选中的 pipeline)
    - `method_pipeline` (完整)
    - `training_and_optimization` (完整)
    - `theoretical_and_complexity` (可选)
  - **不需要**的信息（会被自动过滤）：
    - `experimental_guidance` (实验指导，不属于 Methods 部分)
    - `integration_strategy.evaluated_combinations` (只需要选中的 pipeline)
    - `method_context.target_scenario`, `keywords_alignment` (非必需)
- `temperature`: 生成温度（默认 0.7）
- `max_tokens`: 最大 token 数（默认 12000，因为内容更详细）
- `model`: 模型名称（可选，使用服务默认值）

## 输出结构

生成的 LaTeX Methods 部分包含：

1. **Overview**: 基于 `method_context` 的研究问题和问题缺口，概述三个改进模块（A*, B*, C*）和整体架构
2. **Module A***: 基于 `module_blueprints.modules[0]` 的详细描述
   - 原始模块 A 的角色和机制
   - 识别的弱点
   - 改进设计（A*）的具体变化
   - 工作流程变化
   - 数学公式（如果提供）
3. **Module B***: 基于 `module_blueprints.modules[1]` 的详细描述
   - 强调如何基于 Module A* 构建
   - 连接细节（数据格式、操作步骤）
4. **Module C***: 基于 `module_blueprints.modules[2]` 的详细描述
   - 强调如何扩展 Module B*
5. **Method Pipeline**: 基于 `method_pipeline.stages` 的详细阶段描述
   - 每个阶段的输入/输出、操作、数学公式
   - 阶段间的信息流
6. **Training and Optimization**: 基于 `training_and_optimization` 的训练细节
   - 损失函数和优化策略
   - 超参数说明
   - 正则化和约束
   - 训练伪代码摘要
7. **Theoretical Analysis** (可选): 基于 `theoretical_and_complexity` 的理论分析
   - 假设、保证、复杂度分析

## 特性

- ✅ 基于详细的 JSON 方法设计生成 Methods 部分
- ✅ 自动提取和整合所有相关实现细节
- ✅ 强调具体的实现步骤、数据格式和操作
- ✅ 自动重试机制（最多 3 次）
- ✅ 温度递减策略（重试时更确定性）
- ✅ LaTeX 块自动提取
- ✅ 完整的错误处理和日志记录

## 与 InnovationSynthesisAgent 的关系

`MethodsWritingAgent` **专门设计**用于处理 `InnovationSynthesisAgent` 的输出：

- **InnovationSynthesisAgent**: 生成详细的方法设计（JSON 格式，强调实现细节、模块改进、集成策略、训练过程等）
- **MethodsWritingAgent**: 将 JSON 方法设计转换为学术论文的 Methods 部分（LaTeX 格式，强调理论表述和学术写作规范）

**工作流程**：
1. 使用 `InnovationSynthesisAgent.generate_innovation_plan()` 生成方法设计 JSON
2. 将 JSON 传递给 `MethodsWritingAgent.generate_methods_section()`
3. 获得结构化的 LaTeX Methods 章节，可直接用于论文写作

## JSON 结构要求

`innovation_json` 可以包含完整的 JSON（由 `InnovationSynthesisAgent` 生成），Agent 会自动提取以下关键信息：

**必需的关键信息：**
- `final_problem_statement`: 一句话描述实际问题（用于 Methods 引言）
- `final_method_proposal_text`: 详细方法提案，包含实现步骤、数据形状、张量维度和执行流程
- `method_context.research_question`: 研究问题
- `method_context.problem_gap`: 问题缺口
- `module_blueprints.modules[]`: 三个模块的蓝图（原始角色、弱点、改进设计）
- `integration_strategy.selected_pipeline`: 选中的管道和连接细节
- `method_pipeline.stages[]`: 方法管道的各个阶段
- `training_and_optimization`: 训练和优化细节

**可选信息：**
- `theoretical_and_complexity`: 理论分析（如果存在会被使用）

**自动过滤的信息（不需要）：**
- `experimental_guidance`: 实验指导（不属于 Methods 部分）
- `integration_strategy.evaluated_combinations`: 评估过的组合（只需要选中的）
- `method_context.target_scenario`, `keywords_alignment`: 非必需背景信息

