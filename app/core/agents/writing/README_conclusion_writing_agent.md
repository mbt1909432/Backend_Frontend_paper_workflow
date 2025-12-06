# ConclusionWritingAgent 使用说明

## 概述

`ConclusionWritingAgent` 是一个专门用于撰写学术论文 Conclusion 部分的 Agent。它基于方法描述、检索到的相关论文和实验结果，生成符合 NeurIPS/ICLR/ICML/CVPR/ACL 级别标准的 LaTeX Conclusion 章节，包括：

- SOTA 方法及其特征总结
- 现有方法的局限性识别
- 新方法解决的问题描述
- 提出的方法及其如何解决这些局限性
- 实验结果的简洁总结
- 整体贡献总结
- 未来研究方向建议

## 使用方法

### 基本示例

```python
from app.services.openai_service import OpenAIService
from app.core.agents.writing.conclusion_writing_agent import ConclusionWritingAgent
from pathlib import Path

# 初始化服务
openai_service = OpenAIService()

# 初始化 Agent
conclusion_agent = ConclusionWritingAgent(openai_service=openai_service)

# 读取 Methods LaTeX 文件（从 methods_writing_agent 生成）
methods_latex_path = Path("generated/methods/innovation_synthesis_methods.tex")
methods_latex_content = methods_latex_path.read_text(encoding="utf-8")

# 读取 Experiment LaTeX 文件（从 main_results_writing_agent 生成）
experiment_latex_path = Path("generated/main_results/innovation_synthesis_main_results.tex")
experiment_latex_content = experiment_latex_path.read_text(encoding="utf-8")

# 生成 Conclusion 部分
result = await conclusion_agent.generate_conclusion_section(
    methods_latex_content=methods_latex_content,
    experiment_latex_content=experiment_latex_content,
    innovation_json=innovation_json,  # 可选：提供 innovation_synthesis.json 以增强准确性
    temperature=0.7,
    max_tokens=6000
)

# 获取生成的 LaTeX 内容
latex_content = result["content"]
print(latex_content)
```

### 最小化示例（仅必需参数）

```python
# 直接传入两个 LaTeX 字符串
methods_latex = """
\\section{Method}
...
"""

experiment_latex = """
\\section{Experiment}
...
"""

result = await conclusion_agent.generate_conclusion_section(
    methods_latex_content=methods_latex,
    experiment_latex_content=experiment_latex
)

latex_content = result["content"]
```

### 使用 innovation_synthesis.json 增强准确性（推荐）

```python
import json
from pathlib import Path

# 读取 innovation_synthesis.json（从 InnovationSynthesisAgent 生成）
innovation_json_path = Path("artifact/innovation_synthesis.json")
innovation_json = json.loads(innovation_json_path.read_text(encoding="utf-8"))["output"]

# 生成 Conclusion（使用 JSON 中的结构化信息）
result = await conclusion_agent.generate_conclusion_section(
    methods_latex_content=methods_latex_content,
    experiment_latex_content=experiment_latex_content,
    innovation_json=innovation_json  # 提供 JSON 以确保方法名称、问题陈述等的一致性
)

latex_content = result["content"]
```

## 参数说明

### 必需参数

- `methods_latex_content` (str): **必需**，Methods 部分的完整 LaTeX 内容
  - 这应该是从 `MethodsWritingAgent` 生成的 LaTeX 文件内容
  - 文件通常命名为 `innovation_synthesis_methods.tex`
  - Agent 会从此内容中提取方法名称、关键创新、架构等信息

- `experiment_latex_content` (str): **必需**，Experiment 部分的完整 LaTeX 内容
  - 这应该是从 `MainResultsWritingAgent` 生成的 LaTeX 文件内容
  - 文件通常命名为 `innovation_synthesis_main_results.tex`
  - Agent 会从此内容中提取基准、结果、发现等信息

### 可选参数

- `innovation_json` (Optional[Dict[str, Any]]): Innovation synthesis JSON（可选，但强烈推荐）
  - 如果提供，Agent 会优先使用 JSON 中的结构化信息，确保：
    - **方法名称一致性**: 使用 `final_proposal_topic` 作为方法名称，在整个 Conclusion 中保持一致
    - **问题陈述准确性**: 使用 `final_problem_statement` 作为问题陈述
    - **局限性准确性**: 使用 `module_blueprints.modules[].weaknesses` 中的弱点列表，比从 LaTeX 提取更准确
    - **创新点清晰性**: 使用 `module_blueprints.modules[].improvement` 和 `integration_strategy.selected_pipeline.rationale` 描述方法如何解决局限性
  - JSON 应包含以下字段（Agent 会自动提取需要的部分）：
    - `final_proposal_topic`: 方法名称
    - `final_problem_statement`: 问题陈述
    - `final_method_proposal_text`: 方法提案摘要
    - `method_context.research_question`: 研究问题
    - `method_context.problem_gap`: 问题缺口
    - `module_blueprints.modules[].weaknesses`: 各模块的弱点列表
    - `module_blueprints.modules[].improvement`: 各模块的改进设计
    - `integration_strategy.selected_pipeline.rationale`: 选择该管道的理由
  - 如果未提供，Agent 会从 LaTeX 内容中提取信息（向后兼容）

- `temperature` (float): 生成温度，默认 `0.7`
  - 重试时会递减（每次降低 0.05，下限 0.3）

- `max_tokens` (int): 最大 token 数，默认 `6000`

- `model` (Optional[str]): 模型名称，默认 `None`（使用服务默认值）

## 输出格式

Agent 返回一个字典，包含：

```python
{
    "content": str,        # 提取的 LaTeX Conclusion 内容
    "raw_response": str,   # 原始响应
    "usage": dict          # Token 使用统计
}
```

生成的 LaTeX 结构：

```latex
\section{Conclusion}

[开场段落：问题陈述和方法概述]

[SOTA 方法总结]

[现有方法局限性]

[我们的方法解决方案]

[实验结果总结]

\paragraph{Contributions.}

\begin{itemize}
    \item [贡献 1]
    \item [贡献 2]
    \item [贡献 3]
    \item [贡献 4]
\end{itemize}

\paragraph{Future Work.}

[未来方向 1]
[未来方向 2]
[未来方向 3]
```

## 特性

- ✅ 基于检索论文生成严谨的 SOTA 方法总结和局限性分析
- ✅ 自动生成符合顶级会议标准的 Conclusion 结构
- ✅ 支持实验结果摘要和额外上下文
- ✅ 自动重试机制（最多 3 次）
- ✅ 温度递减策略（重试时更确定性）
- ✅ LaTeX 块自动提取
- ✅ 完整的错误处理和日志记录
- ✅ 正式学术语调，避免夸大
- ✅ 具体的、可操作的未来研究方向

## 关键约束

1. **方法名称提取**: 
   - **优先使用**: 如果提供了 `innovation_json`，使用 `final_proposal_topic` 作为方法名称
   - **备选方案**: 否则从 Methods LaTeX 内容中提取方法名称
   - 在整个 Conclusion 中一致使用提取的方法名称
2. **基于提供的内容**: 
   - **优先使用**: 如果提供了 `innovation_json`，优先使用其中的结构化信息（方法名称、问题陈述、局限性、创新点）
   - **补充信息**: 从 Methods 和 Experiment LaTeX 内容中提取其他细节
   - 所有关于 SOTA 方法、局限性和实验结果的声明都应基于提供的内容
3. **不夸大**: 实验性能总结应基于 Experiment 部分中实际报告的结果，避免夸大
4. **逻辑连贯**: 确保从 SOTA 总结 → 局限性 → 我们的方法 → 结果 → 贡献 → 未来工作的流畅逻辑
5. **LaTeX 格式**: 输出完整的 LaTeX 格式，可直接用于论文
6. **数学公式格式**: 所有显示的数学公式必须使用 `\begin{equation} ... \end{equation}` 环境
7. **无引用命令**: 输出中不包含任何引用命令（`\cite`, `\citep` 等）

## 错误处理

- 如果 `methods_latex_content` 为空或 None，会抛出 `ValueError`
- 如果 `experiment_latex_content` 为空或 None，会抛出 `ValueError`
- 如果生成失败（无法提取有效的 LaTeX Conclusion 部分），会重试最多 3 次
- 如果所有重试都失败，会抛出 `ValueError`

## 与其他 Agent 的配合

`ConclusionWritingAgent` 可以与其他写作 Agent 配合使用：

- **上游**: 可以接收 `InnovationSynthesisAgent` 的输出（`innovation_synthesis.json`）作为结构化信息源
  - **强烈推荐**: 提供 `innovation_json` 参数以确保方法名称、问题陈述、局限性等的一致性
  - JSON 中的结构化信息比从 LaTeX 提取更准确，特别是对于方法名称和局限性描述
- **上游**: 可以接收 `MethodsWritingAgent` 的输出作为 Methods LaTeX 内容
- **上游**: 可以接收 `MainResultsWritingAgent` 的输出作为实验结果摘要
- **下游**: 生成的 Conclusion 可以与 `IntroductionWritingAgent`、`MethodsWritingAgent` 和 `MainResultsWritingAgent` 的输出组合成完整论文

## 示例工作流程

### 基本工作流程（仅使用 LaTeX）

```python
from pathlib import Path

# 1. 从 MethodsWritingAgent 生成的 LaTeX 文件读取 Methods 内容
methods_tex_path = Path("generated/methods/innovation_synthesis_methods.tex")
methods_latex = methods_tex_path.read_text(encoding="utf-8")

# 2. 从 MainResultsWritingAgent 生成的 LaTeX 文件读取 Experiment 内容
experiment_tex_path = Path("generated/main_results/innovation_synthesis_main_results.tex")
experiment_latex = experiment_tex_path.read_text(encoding="utf-8")

# 3. 生成 Conclusion
conclusion_result = await conclusion_agent.generate_conclusion_section(
    methods_latex_content=methods_latex,
    experiment_latex_content=experiment_latex
)

# 4. 使用生成的 LaTeX
conclusion_latex = conclusion_result["content"]

# 5. 保存到文件（可选）
conclusion_tex_path = Path("generated/conclusion/innovation_synthesis_conclusion.tex")
conclusion_tex_path.parent.mkdir(parents=True, exist_ok=True)
conclusion_tex_path.write_text(conclusion_latex, encoding="utf-8")
```

### 推荐工作流程（使用 innovation_synthesis.json）

```python
import json
from pathlib import Path

# 1. 读取 innovation_synthesis.json（从 InnovationSynthesisAgent 生成）
innovation_json_path = Path("artifact/innovation_synthesis.json")
innovation_data = json.loads(innovation_json_path.read_text(encoding="utf-8"))
innovation_json = innovation_data["output"]  # 提取 JSON 输出部分

# 2. 读取 Methods LaTeX 内容
methods_tex_path = Path("generated/methods/innovation_synthesis_methods.tex")
methods_latex = methods_tex_path.read_text(encoding="utf-8")

# 3. 读取 Experiment LaTeX 内容
experiment_tex_path = Path("generated/main_results/innovation_synthesis_main_results.tex")
experiment_latex = experiment_tex_path.read_text(encoding="utf-8")

# 4. 生成 Conclusion（使用 JSON 增强准确性）
conclusion_result = await conclusion_agent.generate_conclusion_section(
    methods_latex_content=methods_latex,
    experiment_latex_content=experiment_latex,
    innovation_json=innovation_json  # 提供 JSON 以确保一致性
)

# 5. 使用生成的 LaTeX
conclusion_latex = conclusion_result["content"]

# 6. 保存到文件
conclusion_tex_path = Path("generated/conclusion/innovation_synthesis_conclusion.tex")
conclusion_tex_path.parent.mkdir(parents=True, exist_ok=True)
conclusion_tex_path.write_text(conclusion_latex, encoding="utf-8")
```

## 输出内容说明

生成的 Conclusion 部分包含以下内容：

1. **开场段落**: 简要总结问题陈述和提出的方法
2. **SOTA 方法总结**: 概述现有方法及其特征
3. **局限性分析**: 识别现有方法的关键局限性
4. **我们的方法**: 描述我们的方法如何解决这些局限性
5. **实验结果总结**: 简洁总结主要实验结果和发现
6. **贡献列表**: 使用 `itemize` 环境列出 3-5 个具体贡献
7. **未来工作**: 提供 3 个具体的、可操作的未来研究方向

## 注意事项

- Conclusion 应该与 Introduction 和 Methods 部分保持一致
- 贡献列表应该与 Introduction 中的贡献列表相呼应，但可以从不同角度阐述
- 未来工作应该具体且可操作，避免泛泛而谈
- 实验结果的总结应该简洁，避免重复 Experiment 部分的详细内容

