# IntroductionWritingAgent 使用说明

## 概述

`IntroductionWritingAgent` 是一个专门用于撰写学术论文 Introduction 部分的 Agent。它基于方法描述和检索到的相关论文，生成符合 NeurIPS/ICLR/ICML/CVPR/ACL 级别标准的 LaTeX Introduction 章节，包括：

- 背景段落（领域问题、SOTA 方法概述、挑战性）
- 现有方法的局限性（基于检索论文的严谨批判）
- 向新方法的过渡（作为对已识别缺口的回应）
- 方法的高级概述（功能、优势、新能力）
- 实验性能总结（基准、改进、不夸大）
- 贡献总结（使用 itemize 环境，3-5 个具体贡献）

## 使用方法

### 基本示例

```python
from app.services.openai_service import OpenAIService
from app.core.agents.writing.introduction_writing_agent import IntroductionWritingAgent

# 初始化服务
openai_service = OpenAIService()

# 初始化 Agent
intro_agent = IntroductionWritingAgent(openai_service=openai_service)

# 准备输入数据
method_info = {
    "method_name": "FusionAgent",
    "method_description": """
    FusionAgent is a novel framework that integrates adaptive scene encoding,
    trajectory consistency distillation, and hierarchical policy decoupling
    to address multimodal navigation challenges.
    """
}

retrieved_papers = [
    """
    Paper 1: Mask2Former (Cheng et al., 2022)
    - Method: Transformer-based semantic segmentation with mask classification
    - Limitations: High computational cost, struggles with small objects
    - Results: 57.7% mIoU on Cityscapes
    """,
    """
    Paper 2: Recurrent-MP (Chaplot et al., 2020)
    - Method: Recurrent memory-augmented policy for vision-language navigation
    - Limitations: Limited generalization across environments, slow convergence
    - Results: 62% success rate on R2R dataset
    """,
    """
    Paper 3: EnvDrop (Tan et al., 2019)
    - Method: Environment dropout for robust navigation
    - Limitations: Performance degradation in complex scenes, requires extensive training
    - Results: 59% success rate on R2R dataset
    """
]

# 可选：实验结果摘要
experimental_results = {
    "benchmarks": ["R2R", "RxR", "Cityscapes"],
    "metrics": {
        "Navigation Success": "65% (+3% over best baseline)",
        "SPL": "0.58 (+0.05 over best baseline)",
        "mIoU": "59.2% (+1.5% over best baseline)"
    },
    "key_findings": "Consistent improvements across all benchmarks with superior generalization"
}

# 可选：额外上下文
additional_context = {
    "datasets": ["R2R", "RxR", "Cityscapes", "ADE20K"],
    "tasks": ["Vision-Language Navigation", "Semantic Segmentation"],
    "motivation": "Addressing the gap between robust scene understanding and efficient navigation"
}

# 生成 Introduction 部分
result = await intro_agent.generate_introduction_section(
    method_info=method_info,
    retrieved_papers=retrieved_papers,
    experimental_results=experimental_results,
    additional_context=additional_context,
    temperature=0.7,
    max_tokens=8000
)

# 获取生成的 LaTeX 内容
latex_content = result["content"]
print(latex_content)
```

### 最小化示例（仅必需参数）

```python
result = await intro_agent.generate_introduction_section(
    method_info={
        "method_name": "OurMethod",
        "method_description": "A novel approach that addresses X, Y, and Z."
    },
    retrieved_papers=[
        "Paper 1: Method A does X but suffers from limitation Y.",
        "Paper 2: Method B addresses Y but has limitation Z."
    ]
)

latex_content = result["content"]
```

## 参数说明

### 必需参数

- `method_info` (Dict[str, Any]): 方法信息字典
  - `method_name` (str): **必需**，方法名称，将在整个 Introduction 中一致使用
  - `method_description` (str): **必需**，方法描述，说明方法的核心功能和设计

- `retrieved_papers` (List[str]): **必需**，检索到的论文列表
  - 每个字符串应包含：方法描述、局限性、结果
  - 至少需要 1 篇论文
  - Agent 会自动为每篇论文分配 ID

### 可选参数

- `experimental_results` (Optional[Dict[str, Any]]): 实验结果摘要
  - `benchmarks`: 基准数据集列表
  - `metrics`: 指标和改进情况
  - `key_findings`: 主要发现总结

- `additional_context` (Optional[Dict[str, Any]]): 额外上下文
  - `datasets`: 使用的数据集列表
  - `tasks`: 解决的任务列表
  - `motivation`: 额外的动机或背景信息

- `temperature` (float): 生成温度，默认 `0.7`
  - 重试时会递减（每次降低 0.05，下限 0.3）

- `max_tokens` (int): 最大 token 数，默认 `8000`

- `model` (Optional[str]): 模型名称，默认 `None`（使用服务默认值）

## 输出格式

Agent 返回一个字典，包含：

```python
{
    "content": str,        # 提取的 LaTeX Introduction 内容
    "raw_response": str,   # 原始响应
    "usage": dict          # Token 使用统计
}
```

生成的 LaTeX 结构：

```latex
\section{Introduction}

[背景段落]
[现有方法局限性]
[向新方法的过渡]
[方法高级概述]
[实验性能总结]

\paragraph{Contributions.}

\begin{itemize}
    \item [贡献 1]
    \item [贡献 2]
    \item [贡献 3]
    \item [贡献 4]
\end{itemize}
```

## 特性

- ✅ 基于检索论文生成严谨的背景和局限性分析
- ✅ 自动生成符合顶级会议标准的 Introduction 结构
- ✅ 支持实验结果摘要和额外上下文
- ✅ 自动重试机制（最多 3 次）
- ✅ 温度递减策略（重试时更确定性）
- ✅ LaTeX 块自动提取
- ✅ 完整的错误处理和日志记录
- ✅ 正式学术语调，避免夸大

## 关键约束

1. **方法名称一致性**: 提供的 `method_name` 将在整个 Introduction 中一致使用
2. **基于检索论文**: 所有关于 SOTA 方法和局限性的声明都应基于提供的检索论文
3. **不夸大**: 实验性能总结应基于提供的结果或合理预期，避免夸大
4. **逻辑连贯**: 确保从背景 → 局限性 → 新方法 → 贡献的流畅逻辑
5. **LaTeX 格式**: 输出完整的 LaTeX 格式，可直接用于论文

## 错误处理

- 如果 `method_info` 缺少必需字段（`method_name` 或 `method_description`），会抛出 `ValueError`
- 如果 `retrieved_papers` 为空，会抛出 `ValueError`
- 如果生成失败（无法提取有效的 LaTeX Introduction 部分），会重试最多 3 次
- 如果所有重试都失败，会抛出 `ValueError`

## 与其他 Agent 的配合

`IntroductionWritingAgent` 可以与其他写作 Agent 配合使用：

- **上游**: 可以接收 `InnovationSynthesisAgent` 的输出作为方法描述
- **下游**: 生成的 Introduction 可以与 `MethodsWritingAgent` 和 `MainResultsWritingAgent` 的输出组合成完整论文

## 示例工作流程

```python
# 1. 从 InnovationSynthesisAgent 获取方法信息
innovation_result = await innovation_agent.generate_innovation_plan(...)
method_proposal = innovation_result["json"]["final_method_proposal_text"]
method_name = innovation_result["json"]["final_proposal_topic"]

# 2. 检索相关论文（假设从检索系统获取）
retrieved_papers = await retrieval_system.retrieve_top_k(query, k=5)

# 3. 生成 Introduction
intro_result = await intro_agent.generate_introduction_section(
    method_info={
        "method_name": method_name,
        "method_description": method_proposal
    },
    retrieved_papers=retrieved_papers,
    experimental_results=experimental_results  # 可选
)

# 4. 使用生成的 LaTeX
introduction_latex = intro_result["content"]
```

