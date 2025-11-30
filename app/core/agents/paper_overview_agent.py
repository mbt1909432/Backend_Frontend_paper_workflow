from typing import Dict, Any, Optional, Tuple
import re
import logging
from tenacity import (
    AsyncRetrying,
    retry_if_result,
    stop_after_attempt,
    wait_exponential,
    before_sleep_log,
    RetryError
)
from app.services.openai_service import OpenAIService
from app.utils.logger import logger


class PaperOverviewAgent:
    """Paper Overview Generation Agent - 专门生成论文概览文件"""
    
    SYSTEM_PROMPT = """# Paper Overview Generation Agent

You are a specialized agent responsible for generating paper overview documents.

## Your Task

Generate a comprehensive paper overview file: `[Paper_Title]_[Paper_Type]_paper_overview.txt`

## Output File Format

**File Name**: `[Paper_Title]_[Paper_Type]_paper_overview.txt`

- Example: "Deep_Learning_Method_paper_overview.txt" or "LLM_Survey_paper_overview.txt"

- Paper_Title: Use underscores instead of spaces

- Paper_Type: Method or Survey

## Content Structure

1. **Title**: [Full paper title in English]
   
   **Title Requirements - Must be Polished and Professional:**
   - The title should be concise, clear, and engaging
   - Use professional academic language that accurately reflects the research content
   - Highlight the key innovation, method, or contribution
   - Avoid overly long titles (ideally 8-15 words)
   - Use proper capitalization (Title Case)
   - Make it attractive and memorable while remaining accurate
   - Examples of good titles:
     - "A Novel Deep Learning Framework for Real-Time Object Detection"
     - "Survey of Large Language Models: Architectures, Applications, and Challenges"
     - "Efficient Graph Neural Networks via Sparse Attention Mechanisms"

2. **Paper Type**: [Method or Survey]

   - Method: Method/algorithm papers (e.g., introducing new models, algorithms, techniques)

   - Survey: Survey/review papers (comprehensive review of existing work)

3. **Abstract**: [200-300 words, including background, problem, solution, results, significance]

4. **Research Content**: [What problem, methods, scenarios, goals]

5. **Innovations**: [At least 3 specific, verifiable innovations]

6. **Application Scenarios**: [Realistic application scenarios]

## Requirements

- ALL content in ENGLISH

- Based on user-provided materials only

- Do not fabricate data

- **CRITICAL: You MUST generate an overview even if the provided materials are limited or vague. Use your best judgment to create a reasonable overview based on the available information. Do NOT refuse to generate or ask for more information.**

- Determine Paper Type based on research content:

  - Method: New algorithms, models, techniques

  - Survey: Comprehensive review of existing work

## Writing Quality Requirements

1. **Be Specific, Avoid Vague Generalizations:**

   - ❌ Avoid: "Our method achieves good performance" or "The results are promising"

   - ✅ Use: "Our method achieves 87.3% accuracy on Dataset-X, outperforming baseline Y by 3.2%"

   - Provide concrete numbers, specific techniques, named datasets, and verifiable claims

2. **Avoid AI-Generated Writing Style:**

   - ❌ Avoid: "In recent years, the field has witnessed significant advances..."

   - ❌ Avoid: "This paper presents a novel approach that..."

   - ✅ Use: Direct, clear statements: "We propose X. It works by Y. Experiments show Z."

   - ✅ Use: Natural academic language without excessive buzzwords

3. **Logical Flow and Coherence:**

   - Each paragraph must logically connect to the previous one

   - Use clear transitions: "However", "Furthermore", "Specifically", "In contrast"

   - Abstract should follow: Background → Problem → Method → Results → Significance (in that order)

   - Innovations should be specific, measurable, and build upon each other logically

## Workflow

1. Analyze research content from user-provided materials (provided by orchestrator)

2. Determine Paper Type (Method or Survey) based on research content

3. Generate comprehensive overview with all required sections

## Output Format

⚠️ **CRITICAL**: You cannot save files directly. You must output in the following markdown format:

```path
[Paper_Title]_[Paper_Type]_paper_overview.txt
```

```text
Title: [Full paper title in English - must be polished, professional, concise, and engaging]

Paper Type: [Method or Survey]

Abstract:

[200-300 words abstract including background, problem, solution, results, significance]

Research Content:

[What problem, methods, scenarios, goals]

Innovations:

1. [First innovation - specific and verifiable]

2. [Second innovation - specific and verifiable]

3. [Third innovation - specific and verifiable]

Application Scenarios:

[Realistic application scenarios]
```

**Important**:

- Use ` ```path ` to specify the file name

- Use ` ```text ` to specify the file content

- The orchestrator will parse this markdown and save the file

- Do NOT include any file operations in your response

- **MANDATORY: You MUST output in the exact format above with both ```path and ```text blocks. Even if the input is vague or limited, you must still generate a reasonable overview in the required format. Do NOT output explanations, questions, or any other text outside the markdown blocks.**"""

    def __init__(self, openai_service: OpenAIService):
        self.openai_service = openai_service
    
    def _parse_markdown_output(self, response: str) -> Tuple[Optional[str], Optional[str]]:
        """
        解析 Agent 输出的 markdown 格式，提取文件名和内容
        
        Args:
            response: Agent 的原始响应
            
        Returns:
            (file_name, file_content) 或 (None, None) 如果解析失败
        """
        try:
            # 匹配 ```path ... ``` 块（更宽松的匹配，支持多种格式）
            # 支持 ```path\n...\n``` 或 ```path ... ```（同一行）
            path_pattern = r'```path\s*\n?(.*?)\n?```'
            path_match = re.search(path_pattern, response, re.DOTALL)
            
            # 匹配 ```text ... ``` 块（更宽松的匹配）
            text_pattern = r'```text\s*\n?(.*?)\n?```'
            text_match = re.search(text_pattern, response, re.DOTALL)
            
            if path_match and text_match:
                file_name = path_match.group(1).strip()
                file_content = text_match.group(1).strip()
                
                # 验证文件名格式
                if not file_name or not file_name.endswith('.txt'):
                    logger.warning(f"Invalid file name format: {file_name}")
                
                return file_name, file_content
            else:
                logger.warning("Failed to parse markdown output: missing path or text block")
                if not path_match:
                    logger.warning("Missing ```path block")
                if not text_match:
                    logger.warning("Missing ```text block")
                # 记录完整响应用于调试
                if response:
                    logger.warning(f"Full response that failed to parse:\n{response}")
                else:
                    logger.warning("Empty response received")
                return None, None
                
        except Exception as e:
            logger.error(f"Error parsing markdown output: {str(e)}")
            return None, None
    
    async def _generate_overview_attempt(
        self,
        user_document: str,
        temperature: Optional[float],
        max_tokens: int,
        model: Optional[str],
        attempt_number: int = 1
    ) -> Optional[Dict[str, Any]]:
        """
        单次生成尝试（内部方法，用于重试）
        
        Args:
            user_document: 用户提供的文档内容
            temperature: 温度参数
            max_tokens: 最大token数
            model: 模型名称
            attempt_number: 当前尝试次数
            
        Returns:
            成功时返回结果字典，失败时返回 None
        """
        # 处理 temperature 为 None 的情况，使用默认值
        if temperature is None:
            temperature = 0.7
        
        # 重试时降低 temperature 以提高稳定性
        adjusted_temperature = max(0.3, temperature - (attempt_number - 1) * 0.1)
        
        # 构建消息，重试时增强格式要求提示
        user_content = f"Please generate a paper overview based on the following materials:\n\n{user_document}"
        if attempt_number > 1:
            user_content += "\n\n⚠️ IMPORTANT: You MUST output in the exact format with ```path and ```text blocks. Ensure both blocks are present and properly formatted. Do NOT output explanations or questions outside the markdown blocks."
        
        messages = [
            {
                "role": "system",
                "content": self.SYSTEM_PROMPT
            },
            {
                "role": "user",
                "content": user_content
            }
        ]
        
        # 记录输入信息（用于调试）
        logger.info(f"Attempt {attempt_number}: Generating paper overview")
        logger.debug(f"Input document length: {len(user_document)} characters")
        logger.debug(f"Input document preview: {user_document[:200]}...")
        logger.debug(f"Temperature: {adjusted_temperature}, Max tokens: {max_tokens}, Model: {model}")
        
        # 调用 OpenAI
        raw_response, usage = await self.openai_service.chat_completion(
            messages=messages,
            temperature=adjusted_temperature,
            max_tokens=max_tokens,
            model=model
        )
        
        # 记录完整响应（用于调试）
        logger.debug(f"Attempt {attempt_number}: Full response received (length: {len(raw_response) if raw_response else 0})")
        if raw_response:
            logger.debug(f"Attempt {attempt_number}: Full response content:\n{raw_response}")
        
        # 解析输出
        file_name, file_content = self._parse_markdown_output(raw_response)
        
        if file_name is None or file_content is None:
            # 记录完整的原始响应用于调试
            logger.warning(f"Attempt {attempt_number}: Failed to parse agent output")
            if raw_response:
                logger.warning(f"Attempt {attempt_number}: Full response that failed to parse:\n{raw_response}")
            else:
                logger.warning(f"Attempt {attempt_number}: Empty response received")
            return None
        
        logger.info(f"Paper overview generated successfully on attempt {attempt_number}: {file_name}")
        
        return {
            "file_name": file_name,
            "file_content": file_content,
            "raw_response": raw_response,
            "usage": usage
        }
    
    async def generate_overview(
        self,
        user_document: str,
        temperature: Optional[float] = 0.7,
        max_tokens: int = 4000,
        model: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        生成论文概览（带重试机制）
        
        Args:
            user_document: 用户提供的文档内容
            temperature: 温度参数
            max_tokens: 最大token数
            model: 模型名称
            
        Returns:
            {
                "file_name": str,
                "file_content": str,
                "raw_response": str,
                "usage": dict
            }
            
        Raises:
            ValueError: 如果所有重试都失败
        """
        def is_parse_failed(result: Optional[Dict[str, Any]]) -> bool:
            """检查解析是否失败"""
            return result is None
        
        last_result = None
        total_attempts = 0
        
        try:
            async for attempt in AsyncRetrying(
                stop=stop_after_attempt(3),
                retry=retry_if_result(is_parse_failed),
                wait=wait_exponential(multiplier=1, min=2, max=10),
                before_sleep=before_sleep_log(logger, logging.WARNING)
            ):
                with attempt:
                    # 使用 retry_state 获取准确的尝试次数
                    attempt_number = attempt.retry_state.attempt_number
                    total_attempts = attempt_number
                    
                    logger.info(f"Generating paper overview (attempt {attempt_number}/3)")
                    
                    last_result = await self._generate_overview_attempt(
                        user_document=user_document,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        model=model,
                        attempt_number=attempt_number
                    )
                    
                    if last_result is None:
                        # 返回 None 让 retry_if_result 机制处理重试
                        logger.warning(f"Attempt {attempt_number} failed: parse returned None, will retry")
                        # 不要在这里 return，让 retry 机制继续
                        continue
                    
                    logger.info(f"Paper overview generated successfully on attempt {attempt_number}")
                    return last_result
                    
        except RetryError as e:
            # 所有重试都失败
            logger.error(f"Failed to generate paper overview after {total_attempts} attempts")
            logger.error(f"Last result: {last_result}")
            logger.error(f"Input document was: {user_document[:500]}...")
            raise ValueError(
                "Agent output format is invalid after multiple retries. "
                "Expected markdown format with ```path and ```text blocks. "
                f"Tried {total_attempts} times. "
                "Check logs for full response details."
            ) from e
        
        # 如果 somehow 到达这里，返回最后的结果
        if last_result is None:
            logger.error(f"Unexpected: last_result is None after retry loop. Input: {user_document[:500]}...")
            raise ValueError("Agent output format is invalid. Expected markdown format with ```path and ```text blocks.")
        return last_result
    
    async def generate_overview_stream(
        self,
        user_document: str,
        temperature: Optional[float] = 0.7,
        max_tokens: int = 4000,
        model: Optional[str] = None
    ):
        """
        流式生成论文概览
        
        Args:
            user_document: 用户提供的文档内容
            temperature: 温度参数
            max_tokens: 最大token数
            model: 模型名称
            
        Returns:
            OpenAI 流式响应迭代器
        """
        # 构建消息
        messages = [
            {
                "role": "system",
                "content": self.SYSTEM_PROMPT
            },
            {
                "role": "user",
                "content": f"Please generate a paper overview based on the following materials:\n\n{user_document}"
            }
        ]
        
        # 调用 OpenAI 流式接口
        stream = await self.openai_service.chat_completion_stream(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            model=model
        )
        
        logger.info("Paper overview streaming started")
        return stream

