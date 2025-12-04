from typing import Dict, Any, Optional, Tuple
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
        "experimental_tables": "..."
    }

    ⚠️ 解析与重试逻辑遵循 docs/agent_markdown_parsing.md 中的通用规范：
    - Agent 只输出 markdown 代码块，由 orchestrator 解析。
    - 这里内容块标签统一使用 `json`。
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
   - **ASCII Table Blocks**: Whenever the OCR contains ASCII/pipe tables (e.g., built with `|` and `-` characters), copy the entire block exactly and store it separately in the `table_details` array described below.
   - **Extract dataset information**: Include all details about datasets used in experiments, such as:
     - Dataset names (e.g., "CIFAR-10", "ImageNet", "COCO")
     - Dataset sizes (number of samples, images, etc.)
     - Dataset splits (train/validation/test ratios or counts)
     - Dataset sources and URLs if mentioned
     - Dataset characteristics and properties
     - Preprocessing and augmentation details
     - Any dataset-specific experimental settings
   - **Extract image/figure information**: Include detailed descriptions of all figures, images, diagrams, and visualizations:
     - Figure captions and titles
     - Descriptions of what each figure shows
     - Any textual descriptions of visual content in the paper
     - References to figures in the text (e.g., "Figure 1 shows...", "As illustrated in Figure 2...")
     - Details about visualizations, plots, diagrams, and their interpretations
   - If the paper uses different terminology (e.g., "Results", "Experimental Results", "Evaluation", "Performance Analysis", "Empirical Results"), extract those sections
   - If experimental content is scattered across multiple sections, combine them into a coherent experiments description while maintaining original wording
   - Include descriptions of tables and figures when they are referenced in the text
   - **For ASCII/pipe tables**: capture every header, separator, cell value, and indentation exactly as seen (e.g., tables built with `|` and `-` characters). Do not reformat or trim rows.

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
   - **Include all dataset details** - Extract complete dataset information including names, sizes, splits, sources, and characteristics
   - **Include all figure/image descriptions** - Extract complete descriptions of all figures, including captions, what they show, and any textual references to visual content

## Output JSON Schema

You MUST produce a JSON object with the following fields:

- "reason": string - A brief explanation of:
  - Which section(s) were identified as containing experimental results
  - What type of experiments were found (empirical, theoretical, comparative, etc.)
  - Any challenges or special considerations in the extraction
  - If the experiments section is missing or incomplete, explain why
- "experiments": string - The extracted experiments/results text (can be empty if no experiments found)
- "baselines": array of strings - List of baseline methods/comparison methods mentioned in the paper. Extract all baseline methods, comparison methods, and state-of-the-art methods that are compared against. Each entry should be the method name as it appears in the paper. Can be empty array if no baselines mentioned.
- "datasets": array of strings - List of datasets used in the experiments. Extract all dataset names (e.g., "CIFAR-10", "ImageNet", "COCO"). Include dataset names even if they appear in different sections. Can be empty array if no datasets mentioned.
- "metrics": array of strings - List of evaluation metrics used in the experiments. Extract all metrics mentioned (e.g., "accuracy", "F1-score", "BLEU", "ROUGE", "mAP", "IoU"). Include all metrics used for evaluation, comparison, or reporting. Can be empty array if no metrics mentioned.
- "experimental_tables": string - The content of all experimental tables found in the paper. Extract table captions, table content (as text representation), and any descriptions of tables. Preserve the structure and numerical values as much as possible. Can be empty string if no tables found.
- "table_details": array of strings - Each entry must be a verbatim ASCII/pipe table block copied exactly (including headers, separators, spacing, and duplicated values). Use one array entry per table. If no ASCII tables appear, return an empty array.

Example 1 (good extraction):
{
  "reason": "Extracted the full 'Results' section including 'Main Results', 'Comparison with Baselines', 'Ablation Studies', and 'Qualitative Analysis' subsections. Results include performance metrics, statistical comparisons, detailed analysis, dataset information, and figure descriptions. All content preserved with original wording.",
  "experiments": "## Results\n\n### Dataset\nWe evaluated our method on three benchmark datasets: CIFAR-10 (50,000 training images, 10,000 test images), ImageNet (1.2M training images, 50,000 validation images), and COCO (118K training images, 5K validation images). All images were resized to 224×224 pixels and normalized.\n\n### Main Results\nOur method achieves 95.2% accuracy on the test set, outperforming the baseline by 3.5%...\n\n### Comparison with Baselines\nTable 1 shows the comparison with state-of-the-art methods...\n\n### Ablation Studies\nWe conducted ablation studies to analyze the contribution of each component...\n\n### Qualitative Analysis\nFigure 2 illustrates example outputs from our method. The figure shows three example images: (a) original input, (b) baseline output, and (c) our method output. As can be seen, our method produces more accurate results with fewer artifacts. Figure 3 displays the performance comparison across different datasets, showing consistent improvements across all metrics...",
  "baselines": ["ResNet-50", "VGG-16", "Transformer", "BERT", "GPT-2"],
  "datasets": ["CIFAR-10", "ImageNet", "COCO"],
  "metrics": ["accuracy", "precision", "recall", "F1-score", "mAP", "IoU"],
  "experimental_tables": "Table 1: Comparison with state-of-the-art methods on CIFAR-10, ImageNet, and COCO datasets.\n\nMethod | CIFAR-10 Acc | ImageNet Acc | COCO mAP\n-------|--------------|--------------|----------\nResNet-50 | 92.1% | 76.2% | 38.5\nVGG-16 | 89.3% | 71.5% | 35.2\nTransformer | 91.8% | 75.8% | 37.9\nOur Method | 95.2% | 79.7% | 42.1\n\nTable 2: Ablation study results showing the contribution of each component.\n\nComponent | Accuracy\n----------|---------\nBaseline | 89.2%\n+ Attention | 92.5%\n+ Multi-scale | 94.1%\nFull Model | 95.2%",
  "table_details": [
    "Method | CIFAR-10 Acc | ImageNet Acc | COCO mAP\n-------|--------------|--------------|----------\nResNet-50 | 92.1% | 76.2% | 38.5\nVGG-16 | 89.3% | 71.5% | 35.2\nTransformer | 91.8% | 75.8% | 37.9\nOur Method | 95.2% | 79.7% | 42.1",
    "Component | Accuracy\n----------|---------\nBaseline | 89.2%\n+ Attention | 92.5%\n+ Multi-scale | 94.1%\nFull Model | 95.2%"
  ]
}

Example 2 (scattered experiments):
{
  "reason": "Experimental results found across 'Experimental Results', 'Performance Analysis', and 'Discussion' sections; combined into a coherent description. Includes quantitative metrics, ablation studies, and comparative analysis.",
  "experiments": "## Experimental Results\n\n### Performance Metrics\nWe evaluated our approach on three benchmark datasets...\n\n### Performance Analysis\nOur method shows consistent improvements across all metrics...\n\n### Discussion\nThe experimental results demonstrate that our approach significantly outperforms existing methods...",
  "baselines": ["Method A", "Method B", "Previous Work"],
  "datasets": ["Dataset X", "Dataset Y"],
  "metrics": ["BLEU", "ROUGE-L", "METEOR"],
  "experimental_tables": "Table 1: Performance comparison on Dataset X and Dataset Y.\n\nMethod | Dataset X BLEU | Dataset Y BLEU\n-------|-----------------|----------------\nMethod A | 45.2 | 42.8\nMethod B | 47.1 | 44.3\nOur Method | 52.3 | 49.7",
  "table_details": [
    "Method | Dataset X BLEU | Dataset Y BLEU\n-------|-----------------|----------------\nMethod A | 45.2 | 42.8\nMethod B | 47.1 | 44.3\nOur Method | 52.3 | 49.7"
  ]
}

Example 3 (theoretical paper):
{
  "reason": "The paper is primarily theoretical without empirical experiments. Extracted the theoretical analysis, comparative discussions, and proof sketches from the 'Analysis' and 'Discussion' sections.",
  "experiments": "## Theoretical Analysis\n\n### Complexity Analysis\nWe prove that our algorithm has a time complexity of O(n log n)...\n\n### Comparative Discussion\nCompared to existing approaches, our method provides better theoretical guarantees...\n\n### Proof Sketches\nWe provide proof sketches for the main theoretical results...",
  "baselines": ["Previous Algorithm", "Baseline Method"],
  "datasets": [],
  "metrics": ["time complexity", "space complexity"],
  "experimental_tables": "",
  "table_details": []
}

Example 4 (survey paper):
{
  "reason": "The paper is a survey without original experiments. Extracted the comparative analysis and synthesis of results from reviewed papers, including performance comparisons and trend analysis.",
  "experiments": "## Comparative Analysis\n\n### Performance Comparison\nWe analyzed 50 papers published between 2020-2024. The average accuracy across all methods is 87.3%...\n\n### Trend Analysis\nFigure 3 shows the evolution of performance metrics over time...\n\n### Synthesis of Findings\nOur analysis reveals that transformer-based methods consistently outperform CNN-based approaches...",
  "baselines": ["CNN-based methods", "RNN-based methods", "Transformer-based methods"],
  "datasets": ["Common benchmark datasets"],
  "metrics": ["accuracy", "F1-score"],
  "experimental_tables": "Table 1: Summary of reviewed papers and their performance.\n\nPaper | Method Type | Accuracy\n------|-------------|---------\nPaper A | CNN | 85.2%\nPaper B | RNN | 86.7%\nPaper C | Transformer | 89.1%",
  "table_details": [
    "Paper | Method Type | Accuracy\n------|-------------|---------\nPaper A | CNN | 85.2%\nPaper B | RNN | 86.7%\nPaper C | Transformer | 89.1%"
  ]
}

## Output Format (MANDATORY)

You CANNOT save files directly.
You MUST output in the following markdown format:

```path
experiments.json
```

```json
{
  "reason": "...",
  "experiments": "...",
  "baselines": [...],
  "datasets": [...],
  "metrics": [...],
  "experimental_tables": "...",
  "table_details": [...]
}
```

CRITICAL RULES:

- Must output EXACTLY two code blocks:
  1) one ```path block with the file name `experiments.json`
  2) one ```json block with the JSON content
- Do NOT output any explanations, comments, or questions outside these code blocks.
- The orchestrator will parse this markdown and save the JSON file.
- **JSON STRING ESCAPING**: All string values in the JSON must be properly escaped:
  - Newlines must be escaped as `\\n` (not literal newlines)
  - Double quotes inside strings must be escaped as `\\"` (not literal quotes)
  - Backslashes must be escaped as `\\\\`
  - The JSON must be valid and parseable by `json.loads()`
  - If the experiments content contains code blocks, formulas, or multi-line content, ensure all special characters are properly escaped
"""

    def __init__(self, openai_service: OpenAIService):
        self.openai_service = openai_service

    def _parse_markdown_output(self, response: str) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
        """
        解析 Agent 输出的 markdown 格式，提取文件名和 JSON 内容。

        期望格式:
        ```path
        experiments.json
        ```

        ```json
        {...}
        ```

        Returns:
            (file_name, json_obj) 或 (None, None) 如果解析失败
        """
        if not response:
            logger.warning("Empty response from ExperimentExtractionAgent")
            return None, None

        try:
            # path block
            path_pattern = r"```path\s*\n?(.*?)\n?```"
            path_match = re.search(path_pattern, response, re.DOTALL)

            if not path_match:
                logger.warning("ExperimentExtractionAgent output missing ```path block")
                logger.warning(f"Full response:\n{response}")
                return None, None

            file_name = path_match.group(1).strip()

            # json content block
            json_pattern = r"```json\s*\n?(.*?)\n?```"
            json_match = re.search(json_pattern, response, re.DOTALL)

            if not json_match:
                logger.warning("ExperimentExtractionAgent output missing ```json block")
                logger.warning(f"Full response:\n{response}")
                return None, None

            json_str = json_match.group(1).strip()

            try:
                # Use json_repair.loads() to handle broken/incomplete JSON
                # It automatically checks if JSON is valid and repairs if needed
                # json_repair preserves non-Latin characters (Chinese, Japanese, etc.) by default
                if json_repair is not None:
                    json_obj = json_repair.loads(json_str)
                else:
                    # Fallback to standard json.loads() if json_repair is not available
                    json_obj = json.loads(json_str)
            except (json.JSONDecodeError, ValueError) as e:
                logger.warning(f"Failed to parse JSON from ExperimentExtractionAgent output: {e}")
                logger.warning(f"Raw json content:\n{json_str}")
                return None, None

            # basic schema validation
            if not isinstance(json_obj, dict):
                logger.warning("ExperimentExtractionAgent JSON is not an object")
                return None, None

            required_fields = {"reason", "experiments", "baselines", "datasets", "metrics", "experimental_tables"}
            if not required_fields.issubset(json_obj):
                logger.warning("ExperimentExtractionAgent JSON missing required fields")
                return None, None

            # reason and experiments should be strings (experiments can be empty)
            if not isinstance(json_obj.get("reason"), str):
                logger.warning("ExperimentExtractionAgent JSON 'reason' is not a string")
                return None, None

            if not isinstance(json_obj.get("experiments"), str):
                logger.warning("ExperimentExtractionAgent JSON 'experiments' is not a string")
                return None, None

            # baselines, datasets, metrics should be arrays of strings
            if not isinstance(json_obj.get("baselines"), list):
                logger.warning("ExperimentExtractionAgent JSON 'baselines' is not an array")
                return None, None
            if not all(isinstance(item, str) for item in json_obj.get("baselines", [])):
                logger.warning("ExperimentExtractionAgent JSON 'baselines' contains non-string items")
                return None, None

            if not isinstance(json_obj.get("datasets"), list):
                logger.warning("ExperimentExtractionAgent JSON 'datasets' is not an array")
                return None, None
            if not all(isinstance(item, str) for item in json_obj.get("datasets", [])):
                logger.warning("ExperimentExtractionAgent JSON 'datasets' contains non-string items")
                return None, None

            if not isinstance(json_obj.get("metrics"), list):
                logger.warning("ExperimentExtractionAgent JSON 'metrics' is not an array")
                return None, None
            if not all(isinstance(item, str) for item in json_obj.get("metrics", [])):
                logger.warning("ExperimentExtractionAgent JSON 'metrics' contains non-string items")
                return None, None

            # experimental_tables should be a string (can be empty)
            if not isinstance(json_obj.get("experimental_tables"), str):
                logger.warning("ExperimentExtractionAgent JSON 'experimental_tables' is not a string")
                return None, None

            return file_name, json_obj

        except Exception as e:
            logger.error(f"Error parsing ExperimentExtractionAgent markdown output: {e}")
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
            temperature = 0.3  # Lower temperature for more consistent extraction

        # 重试时降低 temperature 以提高稳定性
        adjusted_temperature = max(0.1, temperature - (attempt_number - 1) * 0.05)

        user_content = f"""Extract the experiments/results section from the following academic paper:

**Title**: {paper_title}

**Full Paper Content**:
{paper_content}

Please extract the complete experiments/results section following the specification."""

        if attempt_number > 1:
            user_content += (
                "\n\n⚠️ IMPORTANT: You MUST output in the exact format with ```path and ```json blocks. "
                "Ensure both blocks are present and properly formatted. "
                "Do NOT output explanations or questions outside the markdown blocks."
            )

        messages = [
            {"role": "system", "content": self.SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ]

        logger.info(f"ExperimentExtractionAgent attempt {attempt_number}: extracting experiments for paper: {paper_title}")
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
            max_tokens: 最大 token 数（默认 40000，因为 experiments 可能很长，需要足够空间完成 JSON 输出）
            model: 使用的模型（可选，使用服务默认值）

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
                "Expected markdown with ```path and ```json blocks producing a valid JSON object."
            ) from e

        if last_result is None:
            logger.error(
                f"ExperimentExtractionAgent unexpected state: last_result is None after retry loop. Paper: {paper_title}"
            )
            raise ValueError(
                "ExperimentExtractionAgent output format is invalid. "
                "Expected markdown with ```path and ```json blocks producing a valid JSON object."
            )

        return last_result


async def example_usage() -> None:
    """
    Example usage for manual testing:
    - 初始化 OpenAIService（依赖你的全局配置，例如 API key、base_url、model 等）
    - 调用 ExperimentExtractionAgent 提取 experiments
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
    We collected 1000 academic papers from various domains...
    
    ### Model Architecture
    Our approach uses a transformer-based architecture...
    
    ## Results
    
    ### Main Results
    Our method achieves 92.5% accuracy on the test set, outperforming the baseline by 4.2%...
    
    ### Comparison with Baselines
    Table 1 shows the comparison with state-of-the-art methods. Our approach consistently outperforms all baselines...
    
    ### Ablation Studies
    We conducted ablation studies to analyze the contribution of each component. Removing the attention mechanism reduces performance by 3.1%...
    
    ### Qualitative Analysis
    Figure 2 illustrates example outputs from our method. The generated text shows improved coherence and domain-specific terminology...
    
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

