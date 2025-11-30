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


class MethodologyExtractionAgent:
    """
    Methodology Extraction Agent

    负责从论文的 Markdown 文件中提取 methodology 与 problem statement 两部分，输出 JSON：
    {
        "reason": "...",
        "problem_statement": "...",
        "methodology": "..."
    }

    ⚠️ 解析与重试逻辑遵循 docs/agent_markdown_parsing.md 中的通用规范：
    - Agent 只输出 markdown 代码块，由 orchestrator 解析。
    - 这里内容块标签统一使用 `json`。
    """

    SYSTEM_PROMPT = """# Methodology Extraction Agent

You are a specialized agent that extracts the **problem statement** and **methodology section** from academic paper content.

## Your Task

Given the full text content of an academic paper (extracted from OCR), you must:

1. **Identify the methodology section**: The methodology section typically includes:
   - Research methods and approaches
   - Experimental setup and procedures
   - Data collection and processing methods
   - Algorithm descriptions
   - Model architectures and training procedures
   - Evaluation metrics and protocols
   - Implementation details

2. **Extract the complete methodology content**: 
   - Extract the entire methodology section, including all subsections (e.g., "Dataset", "Experimental Setup", "Training Details", etc.)
   - Preserve the structure and formatting as much as possible
   - Include relevant technical details, formulas, algorithms, and procedures
   - If the paper uses different terminology (e.g., "Methods", "Approach", "Technical Details", "Experimental Methodology"), extract those sections
   - If methodology is scattered across multiple sections, combine them into a coherent methodology description

3. **Identify the original problem statement**:
   - Capture the exact wording that defines the research problem, objective, or question the paper addresses
   - Typically appears in sections named "Problem Statement", "Problem Formulation", "Task Definition", or introductory paragraphs describing the challenge
   - Include key assumptions, constraints, datasets/tasks referenced when framing the problem
   - If the problem statement is scattered, combine the relevant sentences into one coherent description

4. **Handle edge cases**:
   - If no explicit methodology section exists, extract relevant methodological content from sections like "Approach", "Technical Details", "Implementation", or "Experimental Setup"
   - If the paper is a survey/review without original methodology, extract the methodology used in the survey itself (e.g., how papers were selected, how analysis was conducted)
   - If methodology or the problem statement is very brief or missing, indicate this in the reason field

## Output JSON Schema

You MUST produce a JSON object with the following fields:

- "reason": string - A brief explanation of:
  - Which section(s) were identified as containing methodology and the problem statement
  - What type of methodology was found (experimental, theoretical, computational, etc.)
  - Any challenges or special considerations in the extraction
  - If either section is missing or incomplete, explain why
- "problem_statement": string - The extracted problem statement (can be empty if no explicit statement found)
- "methodology": string - The extracted methodology text (can be empty if no methodology found)

Example 1 (good extraction):
{
  "reason": "Extracted 'Problem Statement' from the introduction and the full 'Methodology' section including 'Dataset', 'Model Architecture', 'Training Procedure', and 'Evaluation Metrics'.",
  "problem_statement": "## Problem Statement\n\nLarge Language Models (LLMs) struggle to provide consistent writing assistance for specialized academic domains. We study how to adapt LLMs to domain-specific writing tasks under limited supervision.",
  "methodology": "## Methodology\n\n### Dataset\nWe used the XYZ dataset containing 10,000 samples...\n\n### Model Architecture\nOur model consists of three main components...\n\n### Training Procedure\nWe trained the model for 100 epochs with a learning rate of 0.001...\n\n### Evaluation Metrics\nWe evaluated our approach using accuracy, precision, and recall..."
}

Example 2 (scattered methodology):
{
  "reason": "Problem statement located in 'Task Definition'. Methodology content found across 'Approach', 'Experimental Setup', and 'Implementation Details'; combined into a coherent description.",
  "problem_statement": "### Task Definition\nGiven a set of multimodal documents, the task is to align textual summaries with visual evidence while minimizing hallucination.",
  "methodology": "## Methodology\n\n### Approach\nOur approach consists of three stages...\n\n### Experimental Setup\nWe evaluated our method on three datasets...\n\n### Implementation Details\nAll experiments were conducted using PyTorch..."
}

Example 3 (missing methodology):
{
  "reason": "The paper is a survey without an explicit methodology section. Extracted the survey's problem framing from the introduction and summarized the methodology covering selection criteria and categorization.",
  "problem_statement": "## Survey Objective\nWe investigate how LLM-based code assistants impact software engineering productivity across different company sizes.",
  "methodology": "## Survey Methodology\n\nWe conducted a systematic review of papers published between 2020-2024. Papers were selected based on the following criteria: (1) published in top-tier venues, (2) focus on the target domain, (3) contain experimental results. We categorized papers into three groups..."
}

## Output Format (MANDATORY)

You CANNOT save files directly.
You MUST output in the following markdown format:

```path
methodology.json
```

```json
{
  "reason": "...",
  "problem_statement": "...",
  "methodology": "..."
}
```

CRITICAL RULES:

- Must output EXACTLY two code blocks:
  1) one ```path block with the file name `methodology.json`
  2) one ```json block with the JSON content
- Do NOT output any explanations, comments, or questions outside these code blocks.
- The orchestrator will parse this markdown and save the JSON file.
- **JSON STRING ESCAPING**: All string values in the JSON must be properly escaped:
  - Newlines must be escaped as `\\n` (not literal newlines)
  - Double quotes inside strings must be escaped as `\\"` (not literal quotes)
  - Backslashes must be escaped as `\\\\`
  - The JSON must be valid and parseable by `json.loads()`
  - If the methodology or problem_statement contains code blocks, formulas, or multi-line content, ensure all special characters are properly escaped
"""

    def __init__(self, openai_service: OpenAIService):
        self.openai_service = openai_service

    def _parse_markdown_output(self, response: str) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
        """
        解析 Agent 输出的 markdown 格式，提取文件名和 JSON 内容。

        期望格式:
        ```path
        methodology.json
        ```

        ```json
        {...}
        ```

        Returns:
            (file_name, json_obj) 或 (None, None) 如果解析失败
        """
        if not response:
            logger.warning("Empty response from MethodologyExtractionAgent")
            return None, None

        try:
            # path block
            path_pattern = r"```path\s*\n?(.*?)\n?```"
            path_match = re.search(path_pattern, response, re.DOTALL)

            if not path_match:
                logger.warning("MethodologyExtractionAgent output missing ```path block")
                logger.warning(f"Full response:\n{response}")
                return None, None

            file_name = path_match.group(1).strip()

            # json content block
            json_pattern = r"```json\s*\n?(.*?)\n?```"
            json_match = re.search(json_pattern, response, re.DOTALL)

            if not json_match:
                logger.warning("MethodologyExtractionAgent output missing ```json block")
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
                logger.warning(f"Failed to parse JSON from MethodologyExtractionAgent output: {e}")
                logger.warning(f"Raw json content:\n{json_str}")
                return None, None

            # basic schema validation
            if not isinstance(json_obj, dict):
                logger.warning("MethodologyExtractionAgent JSON is not an object")
                return None, None

            required_fields = {"reason", "problem_statement", "methodology"}
            if not required_fields.issubset(json_obj):
                logger.warning("MethodologyExtractionAgent JSON missing required fields")
                return None, None

            # reason and methodology should be strings (methodology can be empty)
            if not isinstance(json_obj.get("reason"), str):
                logger.warning("MethodologyExtractionAgent JSON 'reason' is not a string")
                return None, None

            if not isinstance(json_obj.get("problem_statement"), str):
                logger.warning("MethodologyExtractionAgent JSON 'problem_statement' is not a string")
                return None, None

            if not isinstance(json_obj.get("methodology"), str):
                logger.warning("MethodologyExtractionAgent JSON 'methodology' is not a string")
                return None, None

            return file_name, json_obj

        except Exception as e:
            logger.error(f"Error parsing MethodologyExtractionAgent markdown output: {e}")
            logger.error(f"Full response:\n{response}")
            return None, None

    async def _extract_methodology_attempt(
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

        user_content = f"""Extract the methodology section from the following academic paper:

**Title**: {paper_title}

**Full Paper Content**:
{paper_content}

Please extract the problem statement and the complete methodology section following the specification."""

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

        logger.info(f"MethodologyExtractionAgent attempt {attempt_number}: extracting methodology for paper: {paper_title}")
        logger.debug(f"Paper content length: {len(paper_content)} characters")

        raw_response, usage = await self.openai_service.chat_completion(
            messages=messages,
            temperature=adjusted_temperature,
            max_tokens=max_tokens,
            model=model,
        )

        file_name, json_obj = self._parse_markdown_output(raw_response)
        if file_name is None or json_obj is None:
            logger.warning(f"MethodologyExtractionAgent attempt {attempt_number}: parse failed")
            return None

        logger.info(f"MethodologyExtractionAgent succeeded on attempt {attempt_number}: {file_name}")

        return {
            "file_name": file_name,
            "json": json_obj,
            "raw_response": raw_response,
            "usage": usage,
        }

    async def extract_methodology(
        self,
        paper_title: str,
        paper_content: str,
        temperature: Optional[float] = 0.3,
        max_tokens: int = 40000,
        model: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        对外主方法：提取论文的 problem statement 与 methodology（带重试）

        Args:
            paper_title: 论文标题
            paper_content: 论文的完整文本内容（通常是 OCR 提取的文本）
            temperature: 生成温度（默认 0.3，较低以获得更一致的提取）
            max_tokens: 最大 token 数（默认 40000，因为 methodology 可能很长，需要足够空间完成 JSON 输出）
            model: 使用的模型（可选，使用服务默认值）

        Returns:
            {
                "file_name": "methodology.json",
                "json": {
                    "reason": str,
                    "problem_statement": str,
                    "methodology": str,
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

                    last_result = await self._extract_methodology_attempt(
                        paper_title=paper_title,
                        paper_content=paper_content,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        model=model,
                        attempt_number=attempt_number,
                    )

                    if last_result is None:
                        logger.warning(
                            f"MethodologyExtractionAgent attempt {attempt_number} failed to parse, will retry (if attempts left)"
                        )
                        continue

                    logger.info(f"MethodologyExtractionAgent succeeded after {attempt_number} attempts")
                    return last_result

        except RetryError as e:
            logger.error(f"MethodologyExtractionAgent failed after {total_attempts} attempts")
            logger.error(f"Last result: {last_result}")
            logger.error(f"Paper title: {paper_title}")
            raise ValueError(
                "MethodologyExtractionAgent output format is invalid after multiple retries. "
                "Expected markdown with ```path and ```json blocks producing a valid JSON object."
            ) from e

        if last_result is None:
            logger.error(
                f"MethodologyExtractionAgent unexpected state: last_result is None after retry loop. Paper: {paper_title}"
            )
            raise ValueError(
                "MethodologyExtractionAgent output format is invalid. "
                "Expected markdown with ```path and ```json blocks producing a valid JSON object."
            )

        return last_result


async def example_usage() -> None:
    """
    Example usage for manual testing:
    - 初始化 OpenAIService（依赖你的全局配置，例如 API key、base_url、model 等）
    - 调用 MethodologyExtractionAgent 提取 methodology
    """
    openai_service = OpenAIService()
    agent = MethodologyExtractionAgent(openai_service=openai_service)

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
    
    ### Training Procedure
    We trained the model for 50 epochs with a learning rate of 0.0001...
    
    ## Results
    Our experiments show significant improvements...
    """
    
    result = await agent.extract_methodology(
        paper_title=sample_title,
        paper_content=sample_content,
    )

    print("=== MethodologyExtractionAgent Demo ===")
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

