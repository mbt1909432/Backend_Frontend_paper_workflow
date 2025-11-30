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


class QueryRewriteAgent:
    """
    Query Rewrite Agent

    负责将用户原始 query 重写为 4 个检索关键词，输出 JSON：
    {
        "reason": "...",
        "keywords": ["k1", "k2", "k3", "k4"]
    }

    ⚠️ 解析与重试逻辑遵循 docs/agent_markdown_parsing.md 中的通用规范：
    - Agent 只输出 markdown 代码块，由 orchestrator 解析。
    - 这里内容块标签统一使用 `json`。
    """

    SYSTEM_PROMPT = """# Query Rewrite Agent

You are a specialized agent that rewrites a user's free-form academic query
into exactly 4 high-quality search **query phrases** for arXiv / academic search.

## Your Task

Given the user's original query (which may be in Chinese or English),
you must:

1. **Extract core research topics**: The user's input may contain various information including:
   - Personal information (company names, job titles, personal experiences)
   - Work background and responsibilities
   - Research interests and academic topics
   
   You must:
   - **Identify and extract the core research themes** (technical domains, methods, application scenarios)
   - **Filter out irrelevant personal information** (company names, job titles, personal background)
   - **Focus on academic research-related technical concepts, tasks, domains, and methods**

2. **Rewrite into search phrases**: Propose EXACTLY 4 search **query phrases** that are:
   - each phrase should independently express the **full core intent** of the query  
     (e.g. include task + domain + method / model in one phrase, NOT split across multiple items)
   - medium length (about 4-12 words each), like a compact search sentence, not single words
   - suitable for arXiv / academic database search
   - preferably in English (unless the query clearly targets Chinese-only content)
   - focused on the **core technical concepts / tasks / domains / methods**
   - provide 4 slightly different rephrasings / angles of the same full intent
   - NOT describing the **paper type or genre** (e.g. do NOT use words like "survey", "review", "overview", "state of the art", "tutorial", "survey review", "paper", "article")

## Output JSON Schema

You MUST produce a JSON object with the following fields:

- "reason": string - A brief explanation of why these 4 keywords were generated, including:
  - What core research topics were extracted from the user's input
  - How personal information was filtered out (if applicable)
  - Why these specific keywords were chosen to represent the research intent
- "keywords": array of exactly 4 non-empty strings (each is a full query phrase, not a single aspect)

Example 1 (good style - simple query):
{
  "reason": "Extracted the core research topic: LLM applications in academic writing assistance. The user wants to write a survey, but the keywords focus on the technical domain (LLM + academic writing) rather than the paper type. Generated 4 variations covering different angles: general LLM applications, LLM-based tools, AI-driven support, and LLM-powered systems, all focused on academic writing assistance.",
  "keywords": [
    "large language models for academic writing assistance",
    "LLM-based tools for academic paper drafting and editing",
    "AI-driven academic writing support with large language models",
    "LLM-powered systems for improving academic writing quality"
  ]
}

Example 2 (good style - query with personal information):
{
  "reason": "Extracted 4 core research themes from the user's input: (1) AI/ML for digital health optimization, (2) A/B testing for health platforms, (3) NLP/LLM for healthcare efficiency, (4) predictive modeling for health outcomes. Filtered out personal information (company name 'Aescape', job title 'Founding Business Analyst', work responsibilities). Each keyword represents one research direction with its application domain, suitable for academic search.",
  "keywords": [
    "AI and machine learning for digital health and wellness optimization",
    "A/B testing frameworks for health platform patient engagement",
    "NLP and large language models for healthcare delivery efficiency",
    "predictive modeling for health outcomes and risk identification"
  ]
}

Bad keyword examples you MUST AVOID (do not use them or similar ones as standalone keywords):
- "survey"
- "review"
- "survey review"
- "overview"
- "paper"
- "article"

## Output Format (MANDATORY)

You CANNOT save files directly.
You MUST output in the following markdown format:

```path
rewrite.json
```

```json
{
  "reason": "...",
  "keywords": ["k1", "k2", "k3", "k4"]
}
```

CRITICAL RULES:

- Must output EXACTLY two code blocks:
  1) one ```path block with the file name `rewrite.json`
  2) one ```json block with the JSON content
- Do NOT output any explanations, comments, or questions outside these code blocks.
- The orchestrator will parse this markdown and save the JSON file.
"""

    def __init__(self, openai_service: OpenAIService):
        self.openai_service = openai_service

    def _parse_markdown_output(self, response: str) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
        """
        解析 Agent 输出的 markdown 格式，提取文件名和 JSON 内容。

        期望格式:
        ```path
        rewrite.json
        ```

        ```json
        {...}
        ```

        Returns:
            (file_name, json_obj) 或 (None, None) 如果解析失败
        """
        if not response:
            logger.warning("Empty response from QueryRewriteAgent")
            return None, None

        try:
            # path block
            path_pattern = r"```path\s*\n?(.*?)\n?```"
            path_match = re.search(path_pattern, response, re.DOTALL)

            if not path_match:
                logger.warning("QueryRewriteAgent output missing ```path block")
                logger.warning(f"Full response:\n{response}")
                return None, None

            file_name = path_match.group(1).strip()

            # json content block
            json_pattern = r"```json\s*\n?(.*?)\n?```"
            json_match = re.search(json_pattern, response, re.DOTALL)

            if not json_match:
                logger.warning("QueryRewriteAgent output missing ```json block")
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
                logger.warning(f"Failed to parse JSON from QueryRewriteAgent output: {e}")
                logger.warning(f"Raw json content:\n{json_str}")
                return None, None

            # basic schema validation
            if not isinstance(json_obj, dict):
                logger.warning("QueryRewriteAgent JSON is not an object")
                return None, None

            if "reason" not in json_obj or "keywords" not in json_obj:
                logger.warning("QueryRewriteAgent JSON missing required fields")
                return None, None

            keywords = json_obj.get("keywords")
            if not isinstance(keywords, list) or len(keywords) != 4:
                logger.warning(f"QueryRewriteAgent JSON keywords invalid: {keywords}")
                return None, None

            # ensure non-empty strings
            if not all(isinstance(k, str) and k.strip() for k in keywords):
                logger.warning("QueryRewriteAgent JSON keywords contain empty or non-string items")
                return None, None

            return file_name, json_obj

        except Exception as e:
            logger.error(f"Error parsing QueryRewriteAgent markdown output: {e}")
            logger.error(f"Full response:\n{response}")
            return None, None

    async def _generate_rewrite_attempt(
        self,
        original_query: str,
        temperature: Optional[float],
        max_tokens: int,
        model: Optional[str],
        attempt_number: int = 1,
    ) -> Optional[Dict[str, Any]]:
        """
        单次生成尝试（内部方法，用于重试）
        """
        if temperature is None:
            temperature = 0.7

        # 重试时降低 temperature 以提高稳定性
        adjusted_temperature = max(0.3, temperature - (attempt_number - 1) * 0.1)

        user_content = f"""The user provided the following query for an academic literature search:

{original_query}

Please rewrite this query into EXACTLY 4 high-quality search keywords following the specification."""

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

        logger.info(f"QueryRewriteAgent attempt {attempt_number}: generating keywords")
        logger.debug(f"Original query: {original_query}")

        raw_response, usage = await self.openai_service.chat_completion(
            messages=messages,
            temperature=adjusted_temperature,
            max_tokens=max_tokens,
            model=model,
        )

        file_name, json_obj = self._parse_markdown_output(raw_response)
        if file_name is None or json_obj is None:
            logger.warning(f"QueryRewriteAgent attempt {attempt_number}: parse failed")
            return None

        logger.info(f"QueryRewriteAgent succeeded on attempt {attempt_number}: {file_name}")

        return {
            "file_name": file_name,
            "json": json_obj,
            "raw_response": raw_response,
            "usage": usage,
        }

    async def generate_rewrite(
        self,
        original_query: str,
        temperature: Optional[float] = 0.5,
        max_tokens: int = 512,
        model: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        对外主方法：生成 query rewrite 结果（带重试）

        Returns:
            {
                "file_name": "rewrite.json",
                "json": {
                    "reason": str,
                    "keywords": [str, str, str, str],
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

                    last_result = await self._generate_rewrite_attempt(
                        original_query=original_query,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        model=model,
                        attempt_number=attempt_number,
                    )

                    if last_result is None:
                        logger.warning(
                            f"QueryRewriteAgent attempt {attempt_number} failed to parse, will retry (if attempts left)"
                        )
                        continue

                    logger.info(f"QueryRewriteAgent succeeded after {attempt_number} attempts")
                    return last_result

        except RetryError as e:
            logger.error(f"QueryRewriteAgent failed after {total_attempts} attempts")
            logger.error(f"Last result: {last_result}")
            logger.error(f"Original query: {original_query}")
            raise ValueError(
                "QueryRewriteAgent output format is invalid after multiple retries. "
                "Expected markdown with ```path and ```json blocks producing a valid JSON object."
            ) from e

        if last_result is None:
            logger.error(
                f"QueryRewriteAgent unexpected state: last_result is None after retry loop. Query: {original_query}"
            )
            raise ValueError(
                "QueryRewriteAgent output format is invalid. "
                "Expected markdown with ```path and ```json blocks producing a valid JSON object."
            )

        return last_result
        

async def example_usage() -> None:
    """
    Example usage for manual testing:
    - 初始化 OpenAIService（依赖你的全局配置，例如 API key、base_url、model 等）
    - 调用 QueryRewriteAgent 生成 4 个关键词
    """
    # 这里假设 OpenAIService 可以无参初始化，
    # 如果你项目里需要传配置，请按实际情况修改。
    openai_service = OpenAIService()
    agent = QueryRewriteAgent(openai_service=openai_service)

    sample_query = "我想写一篇关于多模态大模型在医学图像分析中的最新进展综述"
    result = await agent.generate_rewrite(original_query=sample_query)

    print("=== QueryRewriteAgent Demo ===")
    print("Original query:", sample_query)
    print("File name:", result.get("file_name"))
    print("JSON payload:", json.dumps(result.get("json"), ensure_ascii=False, indent=2))

    usage = result.get("usage") or {}
    print("\n--- Token Usage ---")
    # 常见字段：prompt_tokens / completion_tokens / total_tokens，不同 SDK 可能略有差异
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
