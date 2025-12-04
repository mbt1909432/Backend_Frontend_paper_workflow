from typing import Dict, Any, Optional, Tuple, List
import json
import re
import asyncio
import logging
from tenacity import (
    AsyncRetrying,
    retry_if_result,
    stop_after_attempt,
    wait_exponential,
    before_sleep_log,
    RetryError,
)

try:
    import json_repair
except ImportError:
    json_repair = None

from app.services.openai_service import OpenAIService
from app.utils.logger import logger


class ExperimentExtractionAgent:
    """
    Experiment Extraction Agent

    负责从论文的 Markdown 文件中提取实验部分（experiments/results/evaluation），输出 JSON：
    {
        "reason": "...",
        "experiments": "...",
        "baselines": [...],
        "datasets": [...],
        "metrics": [...],
        "experimental_tables": "...",
        "table_details": [...]
    }

    ⚠️ 内部使用 XML 标签格式让 LLM 输出，然后解析为 JSON 供下游使用
    - Agent 输出 XML 标签格式（更可靠，特别是对表格）
    - 解析后转换为 JSON 格式返回给 orchestrator
    """

    SYSTEM_PROMPT = """# Experiment Extraction Agent

You are a specialized agent that extracts the **experimental results and evaluation section** from academic paper content.

## Your Task

Given the full text content of an academic paper (extracted from OCR), you must:

1. **Identify the experiments/results section**: The experiments section typically includes:
   - Experimental results and findings
   - Performance metrics and evaluation scores
   - Comparison with baseline methods
   - Ablation studies and component analysis
   - Statistical analysis and significance tests
   - Tables and figures descriptions
   - Case studies and qualitative analysis
   - Error analysis and failure cases
   - Discussion of experimental findings
   - **Dataset information**: Dataset names, dataset sizes, dataset splits (train/validation/test), dataset sources, dataset characteristics, preprocessing steps
   - **Image/Figure descriptions**: Detailed descriptions of figures, images, diagrams, visualizations, including what they show, captions, and any textual descriptions of visual content

2. **Extract the complete experiments content**: 
   - **CRITICAL: Maintain consistency with the original text** - Preserve the exact wording, terminology, numerical values, punctuation, symbols, and formatting from the original paper as much as possible. Do NOT paraphrase, summarize, translate, reorder, or rewrite the content. Keep the original language and style.
   - **MANDATORY: Copy verbatim** - Every sentence, equation, list item, table row, and figure description must be reproduced exactly as provided in the OCR text. If the source text contains typos or malformed characters, keep them unchanged. Never skip or condense any fragment, even if it looks redundant.
   - Extract the entire experiments/results section, including all subsections (e.g., "Main Results", "Ablation Studies", "Comparison with Baselines", "Qualitative Analysis", "Dataset", "Experimental Setup", etc.)
   - Preserve the structure and formatting as much as possible
   - Include relevant numerical results, tables, figures descriptions, and analysis
   - **MANDATORY: Extract structured information**:
     - **Baselines**: Extract ALL baseline methods, comparison methods, and state-of-the-art methods mentioned anywhere in the paper. Look for sections like "Comparison with Baselines", "Related Work", "Experimental Results", tables comparing methods, etc. Include method names exactly as they appear (e.g., "ResNet-50", "BERT-base", "GPT-2").
     - **Datasets**: Extract ALL dataset names mentioned in the paper. Look in sections like "Dataset", "Experimental Setup", "Results", tables, etc. Include dataset names exactly as they appear (e.g., "CIFAR-10", "ImageNet", "COCO", "GLUE").
     - **Metrics**: Extract ALL evaluation metrics mentioned in the paper. Look for metrics in results sections, tables, figure captions, etc. Include metric names exactly as they appear (e.g., "accuracy", "F1-score", "BLEU", "ROUGE-L", "mAP", "IoU", "perplexity").
   - **Experimental Tables**: Extract the complete content of ALL tables related to experiments. Include table captions, table structure (as text representation), all numerical values, and any descriptions. Preserve the table structure as much as possible. If tables are referenced but not fully described, extract what is available in the text.
   - **ASCII Table Blocks**: Whenever the OCR contains ASCII/pipe tables (e.g., built with `|` and `-` characters), copy the entire block exactly and store it separately in the `<table>` tags inside `<table_details>`.
   - **Extract dataset information**: Include all details about datasets used in experiments
   - **Extract image/figure information**: Include detailed descriptions of all figures, images, diagrams, and visualizations
   - Include descriptions of tables and figures when they are referenced in the text
   - **For ASCII/pipe tables**: capture every header, separator, cell value, and indentation exactly as seen. Do not reformat or trim rows.

3. **Handle edge cases**:
   - If no explicit experiments/results section exists, extract relevant experimental content from sections like "Evaluation", "Performance", "Analysis", or "Discussion"
   - If the paper is theoretical without experimental results, extract any theoretical analysis, proofs, or comparative discussions
   - If the paper is a survey/review, extract the comparative analysis, summary of results from reviewed papers, or synthesis of findings
   - If experiments are very brief or missing, indicate this in the reason field

4. **CRITICAL: Preserve Original Content**:
   - **DO NOT paraphrase or rewrite** - Keep the exact wording, phrases, and sentences from the original paper
   - **DO NOT summarize** - Include full details, not condensed versions
   - **Preserve numerical values exactly** - Keep all numbers, percentages, metrics, measurements, units, and significant digits as they appear in the original
   - **Preserve technical terminology** - Use the same technical terms, abbreviations, and notation as the original
   - **Preserve structure** - Maintain the original section headings, subsection organization, and formatting style
   - **Include all dataset details** - Extract complete dataset information
   - **Include all figure/image descriptions** - Extract complete descriptions of all figures

## Output XML Format

You MUST produce output with the following XML structure:

<reason>
A brief explanation of which sections were identified, what type of experiments were found, and any challenges in extraction
</reason>

<experiments>
The extracted experiments/results text with all original formatting preserved
</experiments>

<baselines>
<baseline>First baseline method name</baseline>
<baseline>Second baseline method name</baseline>
</baselines>

<datasets>
<dataset>First dataset name</dataset>
<dataset>Second dataset name</dataset>
</datasets>

<metrics>
<metric>First metric name</metric>
<metric>Second metric name</metric>
</metrics>

<experimental_tables>
The content of all experimental tables with structure and values preserved
</experimental_tables>

<table_details>
<table>
First ASCII/pipe table block copied exactly
</table>
<table>
Second ASCII/pipe table block
</table>
</table_details>

## Output Format Examples

### Example 1: Complete experimental paper with tables

<reason>Extracted the full 'Results' section including 'Main Results', 'Comparison with Baselines', 'Ablation Studies', and 'Qualitative Analysis' subsections. Results include performance metrics, statistical comparisons, detailed analysis, dataset information, and figure descriptions. All content preserved with original wording.</reason>

<experiments>## Results

### Dataset
We evaluated our method on three benchmark datasets: CIFAR-10 (50,000 training images, 10,000 test images), ImageNet (1.2M training images, 50,000 validation images), and COCO (118K training images, 5K validation images). All images were resized to 224×224 pixels and normalized.

### Main Results
Our method achieves 95.2% accuracy on the test set, outperforming the baseline by 3.5%. The improvement is statistically significant (p < 0.01).

### Comparison with Baselines
Table 1 shows the comparison with state-of-the-art methods. Our approach consistently outperforms all baselines across all three datasets.

### Ablation Studies
We conducted ablation studies to analyze the contribution of each component. The attention mechanism contributes 2.7% to the overall performance, while the multi-scale features add 1.6%.

### Qualitative Analysis
Figure 2 illustrates example outputs from our method. The figure shows three example images: (a) original input, (b) baseline output, and (c) our method output. As can be seen, our method produces more accurate results with fewer artifacts.</experiments>

<baselines>
<baseline>ResNet-50</baseline>
<baseline>VGG-16</baseline>
<baseline>Transformer</baseline>
<baseline>BERT</baseline>
<baseline>GPT-2</baseline>
</baselines>

<datasets>
<dataset>CIFAR-10</dataset>
<dataset>ImageNet</dataset>
<dataset>COCO</dataset>
</datasets>

<metrics>
<metric>accuracy</metric>
<metric>precision</metric>
<metric>recall</metric>
<metric>F1-score</metric>
<metric>mAP</metric>
<metric>IoU</metric>
</metrics>

<experimental_tables>Table 1: Comparison with state-of-the-art methods on CIFAR-10, ImageNet, and COCO datasets.

Method | CIFAR-10 Acc | ImageNet Acc | COCO mAP
-------|--------------|--------------|----------
ResNet-50 | 92.1% | 76.2% | 38.5
VGG-16 | 89.3% | 71.5% | 35.2
Transformer | 91.8% | 75.8% | 37.9
Our Method | 95.2% | 79.7% | 42.1

Table 2: Ablation study results showing the contribution of each component.

Component | Accuracy
----------|---------
Baseline | 89.2%
+ Attention | 92.5%
+ Multi-scale | 94.1%
Full Model | 95.2%</experimental_tables>

<table_details>
<table>Method | CIFAR-10 Acc | ImageNet Acc | COCO mAP
-------|--------------|--------------|----------
ResNet-50 | 92.1% | 76.2% | 38.5
VGG-16 | 89.3% | 71.5% | 35.2
Transformer | 91.8% | 75.8% | 37.9
Our Method | 95.2% | 79.7% | 42.1</table>
<table>Component | Accuracy
----------|---------
Baseline | 89.2%
+ Attention | 92.5%
+ Multi-scale | 94.1%
Full Model | 95.2%</table>
</table_details>

### Example 2: Scattered experiments

<reason>Experimental results found across 'Experimental Results', 'Performance Analysis', and 'Discussion' sections; combined into a coherent description. Includes quantitative metrics, ablation studies, and comparative analysis.</reason>

<experiments>## Experimental Results

### Performance Metrics
We evaluated our approach on three benchmark datasets: Dataset X, Dataset Y, and Dataset Z. The results show consistent improvements across all metrics.

### Performance Analysis
Our method shows consistent improvements across all metrics. On Dataset X, we achieve a BLEU score of 52.3, compared to 47.1 for the previous best method.

### Discussion
The experimental results demonstrate that our approach significantly outperforms existing methods.</experiments>

<baselines>
<baseline>Method A</baseline>
<baseline>Method B</baseline>
<baseline>Previous Work</baseline>
</baselines>

<datasets>
<dataset>Dataset X</dataset>
<dataset>Dataset Y</dataset>
</datasets>

<metrics>
<metric>BLEU</metric>
<metric>ROUGE-L</metric>
<metric>METEOR</metric>
</metrics>

<experimental_tables>Table 1: Performance comparison on Dataset X and Dataset Y.

Method | Dataset X BLEU | Dataset Y BLEU
-------|-----------------|----------------
Method A | 45.2 | 42.8
Method B | 47.1 | 44.3
Our Method | 52.3 | 49.7</experimental_tables>

<table_details>
<table>Method | Dataset X BLEU | Dataset Y BLEU
-------|-----------------|----------------
Method A | 45.2 | 42.8
Method B | 47.1 | 44.3
Our Method | 52.3 | 49.7</table>
</table_details>

### Example 3: Theoretical paper

<reason>The paper is primarily theoretical without empirical experiments. Extracted the theoretical analysis, comparative discussions, and proof sketches from the 'Analysis' and 'Discussion' sections.</reason>

<experiments>## Theoretical Analysis

### Complexity Analysis
We prove that our algorithm has a time complexity of O(n log n) and a space complexity of O(n).

### Comparative Discussion
Compared to existing approaches, our method provides better theoretical guarantees.

### Proof Sketches
We provide proof sketches for the main theoretical results.</experiments>

<baselines>
<baseline>Previous Algorithm</baseline>
<baseline>Baseline Method</baseline>
</baselines>

<datasets>
</datasets>

<metrics>
<metric>time complexity</metric>
<metric>space complexity</metric>
</metrics>

<experimental_tables></experimental_tables>

<table_details>
</table_details>

### Example 4: Survey paper

<reason>The paper is a survey without original experiments. Extracted the comparative analysis and synthesis of results from reviewed papers, including performance comparisons and trend analysis.</reason>

<experiments>## Comparative Analysis

### Performance Comparison
We analyzed 50 papers published between 2020-2024. The average accuracy across all methods is 87.3%.

### Trend Analysis
Figure 3 shows the evolution of performance metrics over time.

### Synthesis of Findings
Our analysis reveals that transformer-based methods consistently outperform CNN-based approaches.</experiments>

<baselines>
<baseline>CNN-based methods</baseline>
<baseline>RNN-based methods</baseline>
<baseline>Transformer-based methods</baseline>
</baselines>

<datasets>
<dataset>Common benchmark datasets</dataset>
</datasets>

<metrics>
<metric>accuracy</metric>
<metric>F1-score</metric>
</metrics>

<experimental_tables>Table 1: Summary of reviewed papers and their performance.

Paper | Method Type | Accuracy
------|-------------|---------
Paper A | CNN | 85.2%
Paper B | RNN | 86.7%
Paper C | Transformer | 89.1%</experimental_tables>

<table_details>
<table>Paper | Method Type | Accuracy
------|-------------|---------
Paper A | CNN | 85.2%
Paper B | RNN | 86.7%
Paper C | Transformer | 89.1%</table>
</table_details>

## CRITICAL RULES

- You MUST output valid XML with all required tags
- All tags must be properly closed
- Content inside tags preserves original formatting naturally (no escaping needed)
- Special characters like |, -, quotes, newlines work naturally in XML
- Empty container tags should still be present (e.g., <datasets></datasets>)
- Do NOT add any text outside the XML structure
- Do NOT add explanations, comments, or questions
"""

    def __init__(self, openai_service: OpenAIService):
        self.openai_service = openai_service

    def _extract_xml_tag_content(self, xml_text: str, tag_name: str) -> Optional[str]:
        """
        从 XML 文本中提取指定标签的内容
        """
        pattern = f"<{tag_name}>(.*?)</{tag_name}>"
        match = re.search(pattern, xml_text, re.DOTALL)
        if match:
            return match.group(1).strip()
        return None

    def _extract_xml_list_items(self, xml_text: str, container_tag: str, item_tag: str) -> List[str]:
        """
        从 XML 文本中提取列表项
        例如: <baselines><baseline>...</baseline><baseline>...</baseline></baselines>
        """
        container_pattern = f"<{container_tag}>(.*?)</{container_tag}>"
        container_match = re.search(container_pattern, xml_text, re.DOTALL | re.IGNORECASE)

        if not container_match:
            return []

        container_content = container_match.group(1)
        item_pattern = f"<{item_tag}>(.*?)</{item_tag}>"
        items = re.findall(item_pattern, container_content, re.DOTALL | re.IGNORECASE)

        return [item.strip() for item in items if item.strip()]

    def _parse_markdown_output(self, response: str) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
        """
        解析 Agent 输出的 XML 格式，转换为 JSON 格式供下游使用

        期望输入格式:
        <reason>...</reason>
        <experiments>...</experiments>
        <baselines><baseline>...</baseline></baselines>
        ...

        输出格式（保持与原代码一致）:
        (file_name, json_obj)
        """
        if not response:
            logger.warning("Empty response from ExperimentExtractionAgent")
            return None, None

        try:
            # 提取各个字段
            reason = self._extract_xml_tag_content(response, "reason")
            experiments = self._extract_xml_tag_content(response, "experiments")
            experimental_tables = self._extract_xml_tag_content(response, "experimental_tables")

            # 提取列表字段
            baselines = self._extract_xml_list_items(response, "baselines", "baseline")
            datasets = self._extract_xml_list_items(response, "datasets", "dataset")
            metrics = self._extract_xml_list_items(response, "metrics", "metric")
            table_details = self._extract_xml_list_items(response, "table_details", "table")

            # 验证必需字段
            if reason is None:
                logger.warning("ExperimentExtractionAgent output missing <reason> tag")
                return None, None

            if experiments is None:
                logger.warning("ExperimentExtractionAgent output missing <experiments> tag")
                return None, None

            # 构建 JSON 对象（保持与原代码格式一致）
            json_obj = {
                "reason": reason,
                "experiments": experiments,
                "baselines": baselines,
                "datasets": datasets,
                "metrics": metrics,
                "experimental_tables": experimental_tables if experimental_tables else "",
                "table_details": table_details,
            }

            logger.info(
                f"Successfully parsed XML output: {len(baselines)} baselines, "
                f"{len(datasets)} datasets, {len(metrics)} metrics, {len(table_details)} tables"
            )

            # 返回固定的文件名和 JSON 对象
            return "experiments.json", json_obj

        except Exception as e:
            logger.error(f"Error parsing ExperimentExtractionAgent XML output: {e}")
            logger.error(f"Full response:\n{response}")
            return None, None

    async def _extract_experiments_attempt(
            self,
            paper_title: str,
            paper_content: str,
            temperature: Optional[float],
            max_tokens: int,
            model: Optional[str],
            attempt_number: int = 1,
    ) -> Optional[Dict[str, Any]]:
        """
        单次提取尝试（内部方法，用于重试）
        """
        if temperature is None:
            temperature = 0.3

        # 重试时降低 temperature 以提高稳定性
        adjusted_temperature = max(0.1, temperature - (attempt_number - 1) * 0.05)

        user_content = f"""Extract the experiments/results section from the following academic paper:

**Title**: {paper_title}

**Full Paper Content**:
{paper_content}

Please extract the complete experiments/results section following the XML format specification."""

        if attempt_number > 1:
            user_content += (
                "\n\n⚠️ IMPORTANT: You MUST output valid XML with all required tags. "
                "Ensure all tags are properly closed and formatted. "
                "Do NOT output explanations or questions outside the XML structure."
            )

        messages = [
            {"role": "system", "content": self.SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ]

        logger.info(
            f"ExperimentExtractionAgent attempt {attempt_number}: extracting experiments for paper: {paper_title}")
        logger.debug(f"Paper content length: {len(paper_content)} characters")

        raw_response, usage = await self.openai_service.chat_completion(
            messages=messages,
            temperature=adjusted_temperature,
            max_tokens=max_tokens,
            model=model,
        )

        file_name, json_obj = self._parse_markdown_output(raw_response)
        if file_name is None or json_obj is None:
            logger.warning(f"ExperimentExtractionAgent attempt {attempt_number}: parse failed")
            return None

        logger.info(f"ExperimentExtractionAgent succeeded on attempt {attempt_number}: {file_name}")

        return {
            "file_name": file_name,
            "json": json_obj,
            "raw_response": raw_response,
            "usage": usage,
        }

    async def extract_experiments(
            self,
            paper_title: str,
            paper_content: str,
            temperature: Optional[float] = 0.3,
            max_tokens: int = 40000,
            model: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        对外主方法：提取论文的实验部分（带重试）

        Args:
            paper_title: 论文标题
            paper_content: 论文的完整文本内容（通常是 OCR 提取的文本）
            temperature: 生成温度（默认 0.3，较低以获得更一致的提取）
            max_tokens: 最大 token 数（默认 40000）
            model: 使用的模型（可选）

        Returns:
            {
                "file_name": "experiments.json",
                "json": {
                    "reason": str,
                    "experiments": str,
                    "baselines": list[str],
                    "datasets": list[str],
                    "metrics": list[str],
                    "experimental_tables": str,
                    "table_details": list[str],
                },
                "raw_response": str,
                "usage": dict,
            }
        """

        def is_parse_failed(result: Optional[Dict[str, Any]]) -> bool:
            return result is None

        last_result: Optional[Dict[str, Any]] = None
        total_attempts = 0

        try:
            async for attempt in AsyncRetrying(
                    stop=stop_after_attempt(3),
                    retry=retry_if_result(is_parse_failed),
                    wait=wait_exponential(multiplier=1, min=1, max=5),
                    before_sleep=before_sleep_log(logger, logging.WARNING),
            ):
                with attempt:
                    attempt_number = attempt.retry_state.attempt_number
                    total_attempts = attempt_number

                    last_result = await self._extract_experiments_attempt(
                        paper_title=paper_title,
                        paper_content=paper_content,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        model=model,
                        attempt_number=attempt_number,
                    )

                    if last_result is None:
                        logger.warning(
                            f"ExperimentExtractionAgent attempt {attempt_number} failed to parse, will retry (if attempts left)"
                        )
                        continue

                    logger.info(f"ExperimentExtractionAgent succeeded after {attempt_number} attempts")
                    return last_result

        except RetryError as e:
            logger.error(f"ExperimentExtractionAgent failed after {total_attempts} attempts")
            logger.error(f"Last result: {last_result}")
            logger.error(f"Paper title: {paper_title}")
            raise ValueError(
                "ExperimentExtractionAgent output format is invalid after multiple retries. "
                "Expected valid XML with all required tags."
            ) from e

        if last_result is None:
            logger.error(
                f"ExperimentExtractionAgent unexpected state: last_result is None after retry loop. Paper: {paper_title}"
            )
            raise ValueError(
                "ExperimentExtractionAgent output format is invalid. "
                "Expected valid XML with all required tags."
            )

        return last_result


async def example_usage() -> None:
    """
    Example usage for manual testing
    """
    openai_service = OpenAIService()
    agent = ExperimentExtractionAgent(openai_service=openai_service)

    sample_title = "Large Language Models for Academic Writing Assistance"
    sample_content = """
    # Large Language Models for Academic Writing Assistance

    ## Abstract
    This paper presents a comprehensive survey of large language models...

    ## Introduction
    Academic writing is a critical skill...

    ## Methodology

    ### Dataset
    We collected 1000 academic papers from various domains including CIFAR-10, ImageNet...

    ### Model Architecture
    Our approach uses a transformer-based architecture...

    ## Results

    ### Main Results
    Our method achieves 92.5% accuracy on the test set, outperforming ResNet-50 baseline by 4.2%...

    ### Comparison with Baselines
    Method | Accuracy | F1-Score
    -------|----------|----------
    ResNet-50 | 88.3% | 0.86
    VGG-16 | 87.1% | 0.84
    Our Method | 92.5% | 0.91

    Table 1 shows the comparison with state-of-the-art methods...

    ### Ablation Studies
    We conducted ablation studies to analyze the contribution of each component...

    ### Qualitative Analysis
    Figure 2 illustrates example outputs from our method...

    ## Discussion
    Our experimental results demonstrate significant improvements...
    """

    result = await agent.extract_experiments(
        paper_title=sample_title,
        paper_content=sample_content,
    )

    print("=== ExperimentExtractionAgent Demo ===")
    print("Paper title:", sample_title)
    print("File name:", result.get("file_name"))
    print("JSON payload:", json.dumps(result.get("json"), ensure_ascii=False, indent=2))

    usage = result.get("usage") or {}
    print("\n--- Token Usage ---")
    print("Raw usage dict:", usage)
    if isinstance(usage, dict):
        prompt_tokens = usage.get("prompt_tokens")
        completion_tokens = usage.get("completion_tokens")
        total_tokens = usage.get("total_tokens") or usage.get("total")
        print(f"prompt_tokens    : {prompt_tokens}")
        print(f"completion_tokens: {completion_tokens}")
        print(f"total_tokens     : {total_tokens}")


if __name__ == "__main__":
    asyncio.run(example_usage())