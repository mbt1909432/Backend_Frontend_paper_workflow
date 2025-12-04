# MainResultsWritingAgent 使用说明（中文）

## 角色与功能
- 负责根据检索到的实验描述与我方方法提案，生成完整的主实验部分（基线筛选、任务结构、全套 LaTeX 表格以及正式叙述）。
- 内部封装 `OpenAIService.chat_completion`，并带有最多三次的退避重试机制，确保返回内容包含所有规定段落。

## 必填输入
| 参数 | 类型 | 说明 |
| --- | --- | --- |
| `experiment_sections` | `List[str]` | 最少 1 个实验摘要字符串，通常来自不同论文的对比实验。会被 `id` + `content` 形式标准化。 |
| `method_proposal` | `str` | 我方方法（模块/改进点/预期收益）的总结，可直接传入 InnovationSynthesisAgent 输出中的 `final_method_proposal_text` 或自定义摘要。 |
| `our_method` | `Dict[str, Any]` | 至少包含 `full_name`，用于表格与正文中标识我方方法名称。 |

## 可选输入
| 参数 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `innovation_plan` | `Optional[Dict[str, Any]]` | `None` | （推荐）直接传入 InnovationSynthesisAgent 的 JSON。包含 `final_proposal_topic`、`final_problem_statement`、`method_context`、`method_pipeline`、`experimental_guidance`（含 `evaluation_setup` / `expected_benefits` / `ablation_plan`）、`integration_strategy.selected_pipeline.expected_effects`、`theoretical_and_complexity.complexity_analysis` 等字段，写作时会逐项引用这些细节。 |
| `temperature` | `float` | `0.6` | 若重试，该值会随尝试次数每次降低 `0.05`，下限 `0.3`。 |
| `max_tokens` | `int` | `9000` | 限制模型输出长度。 |
| `model` | `Optional[str]` | `None` | 显式指定模型；若 `None`，由 `OpenAIService` 默认配置决定。 |

## 输出
成功时返回 `Dict[str, Any]`，结构如下：
```python
{
    "content": "最终正文，已裁剪首尾空白",
    "raw_response": "模型原始输出（含所有段落）",
    "usage": {...}  # OpenAI API 的 tokens 统计
}
```
若三次尝试都缺少 `① Baseline Selection Summary` 段落，会抛出 `ValueError`。

## 约束与提醒
1. 模型系统提示（`SYSTEM_PROMPT`）强制输出四个部分，顺序不可变。
2. 若实验无需显著性检验，必须在任务结构中显式写出“不需要”，并跳过相关表格与段落。
3. 所有表格需遵循 `\label{tab:main_results}` 等固定命名，便于后续 LaTeX 引用。
4. 若输入实验为空或 `our_method` 缺少必要字段，将直接抛出 `ValueError`，请在调用前校验。

## 示例输入
```python
agent = MainResultsWritingAgent(openai_service)
result = await agent.generate_main_results_package(
    experiment_sections=[
        "Paper A: 语义分割 (Cityscapes / ADE20K)，比较 Mask2Former、SegFormer，指标 mIoU。",
        "Paper B: 多模态导航 (R2R / RxR)，比较 Recurrent-MP、EnvDrop，指标 Navigation Success、SPL。",
        "Paper C: 数据效率实验，记录训练成本和 FPS。"
    ],
    method_proposal="""
    我们的方法 FusionAgent 由自适应场景编码 (Module A)、轨迹一致性蒸馏 (Module B)、
    以及层级式策略解耦 (Module C) 组成。预期带来跨数据集泛化与运行效率双重提升。
    """,
    our_method={"full_name": "FusionAgent: Hierarchical Multimodal Policy"},
    innovation_plan=innovation_plan_json  # 即 InnovationSynthesisAgent 的解析结果
)
```
该调用会把所有字段打包进 prompt；若成功返回，`result["content"]` 即为包含四个部分的完整中文/英文主实验稿。

