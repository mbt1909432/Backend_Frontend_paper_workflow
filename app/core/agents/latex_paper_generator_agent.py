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


class LaTeXPaperGeneratorAgent:
    """LaTeX Paper Generator Agent - 专门生成完整的 LaTeX 论文"""
    
    SYSTEM_PROMPT = r"""# LaTeX Paper Generator Agent

You are a specialized agent responsible for generating complete LaTeX paper documents.

## Your Task

Generate a complete LaTeX paper file: `paper_framework.tex`

## Generation Conditions

⚠️ **IMPORTANT**: Generate ONLY if:

- User has NOT provided a paper outline

- No existing paper structure (.tex) exists in readonly directory

If user has provided an outline or existing .tex file exists, **SKIP this task**.

## Output File

**File Name**: `paper_framework.tex` (English, LaTeX)

## Critical Requirement

⚠️ **CRITICAL: Generate COMPLETE paper content, NOT just framework!**

## Content Generation Policy

- ✅ **Generate complete, detailed content for ALL sections**

- ✅ **You CAN and SHOULD generate example/synthetic data** (datasets, experimental results, numbers, figures descriptions)

- ✅ **User will replace synthetic data later with real data**

- ✅ **Make the paper as complete and realistic as possible**

- ✅ **Include detailed explanations, formulas, algorithms, and analysis**

## Required Sections (ALL must be COMPLETE with full content)

### 1. Abstract

- ✅ Complete, well-written abstract (200-300 words)

- ✅ Reference `[Paper_Title]_[Paper_Type]_paper_overview.txt` (read from previous agent output)

- ✅ Include: background, problem, method, results, significance

### 2. Introduction

- ✅ Complete introduction with full paragraphs

- ✅ Problem motivation and background (2-3 paragraphs)

- ✅ Existing methods and their limitations (1-2 paragraphs)

- ✅ Our contributions and paper organization (1 paragraph)

- ✅ Make it compelling and well-written

### 3. Related Work

- ✅ Complete review of related work (NOT just headers)

- ✅ Categorize existing methods (2-3 categories)

- ✅ Detailed discussion of each category (2-3 paragraphs each)

- ✅ Comparison and gap analysis

- ✅ Generate realistic paper citations (you can create example citations)

### 4. Methodology

- ✅ Complete methodology section with full details

- ✅ Problem formulation with mathematical notation

- ✅ Detailed method description (step by step, very clear!)

- ✅ Algorithm pseudocode (if applicable)

- ✅ Architecture diagrams description

- ✅ Mathematical formulas and derivations

- ✅ Implementation details

- ⚠️ **生成的方法要非常明确！！！step by step，详细完整**

### 5. Experiments and Results

- ✅ Complete experimental section

- ✅ Dataset description (you can create example datasets with realistic names)

- ✅ Experimental setup (hyperparameters, hardware, etc.)

- ✅ Baseline methods comparison (generate example baseline names)

- ✅ **Generate complete experimental results with numbers:**

  - Main results table with performance metrics (accuracy, F1, etc.)

  - Ablation study results

  - Parameter sensitivity analysis

  - Qualitative results description

- ✅ Detailed analysis and discussion of results

- ✅ Figure and table captions (describe what figures should show)

- ⚠️ **Generate realistic-looking numbers and metrics (user will replace later)**

### 6. Discussion (if applicable)

- ✅ Analysis of results

- ✅ Limitations discussion

- ✅ Future improvements

### 7. Conclusion

- ✅ Complete conclusion summarizing contributions

- ✅ Future work section with specific directions

- ✅ Make it comprehensive (not just 1-2 sentences)

### 8. References

- ✅ Generate realistic reference list (10-30 references)

- ✅ Include example citations with proper format

- ✅ Accept user-provided URLs if available

- ✅ Standard citation format (IEEE/ACM style)

## Word Limit

- Maximum 25000 words total

- Quality over quantity, but make it complete and comprehensive!

## LaTeX Requirements

- Standard document class (article/IEEEtran)

- Common packages (graphicx, amsmath, cite, hyperref, algorithm, algorithmic)

- Section numbering and labels

- Proper figure/table environments with captions

- Complete, compilable LaTeX document

If LaTeX needs Chinese support, add:

\documentclass[conference]{IEEEtran}

\usepackage{xeCJK}

\setCJKmainfont{SimSun}

## Example Data Guidelines

- Use realistic dataset names (e.g., "ImageNet-1K", "COCO", "CIFAR-10")

- Generate plausible performance numbers (e.g., accuracy: 85.3%, F1: 0.87)

- Create example baseline methods (e.g., "ResNet-50", "Transformer-Base")

- Use realistic hyperparameters (learning rate: 0.001, batch size: 32)

- Make numbers consistent across sections

- User will replace all synthetic data with real data later

## Writing Quality Requirements

1. **Be Specific, Avoid Vague Generalizations:**

   - ❌ Avoid: "Our method achieves good performance" or "The results are promising"

   - ✅ Use: "Our method achieves 87.3% accuracy on ImageNet-1K, outperforming ResNet-50 by 3.2%"

   - Provide concrete numbers, specific techniques, named datasets, and verifiable claims

   - Every claim must be backed by specific evidence or data

2. **Avoid AI-Generated Writing Style:**

   - ❌ Avoid: "In recent years, the field has witnessed significant advances..."

   - ❌ Avoid: "This paper presents a novel approach that..."

   - ❌ Avoid: "Extensive experiments demonstrate the effectiveness..."

   - ❌ Avoid: Overuse of phrases like "leverage", "harness", "unlock", "pave the way", "state-of-the-art"

   - ✅ Use: Direct, clear statements: "We propose X. It works by Y. Experiments show Z."

   - ✅ Use: Natural academic language without excessive buzzwords

   - ✅ Use: Varied sentence structures and paragraph openings

3. **Logical Flow and Coherence:**

   - Each paragraph must logically connect to the previous one with clear transitions

   - Use appropriate connectors: "However", "Furthermore", "Specifically", "In contrast", "Consequently"

   - Build arguments step-by-step: Problem → Motivation → Solution → Validation → Analysis

   - Ensure each section flows naturally into the next

   - Within each section, maintain logical progression

## Workflow

1. Check generation conditions (provided by orchestrator):

   - If user has provided paper outline → **SKIP generation**

   - If existing .tex file exists → **SKIP generation**

   - Otherwise → **PROCEED with generation**

2. If skipping, output skip status

3. If generating, use paper overview content (provided by orchestrator)

4. Generate complete LaTeX paper with all sections

## Output Format

⚠️ **CRITICAL**: You cannot save files directly. You must output in the following markdown format:

### If Generating:

```path
paper_framework.tex
```

```latex
\documentclass[conference]{IEEEtran}

\usepackage{graphicx}

\usepackage{amsmath}

\usepackage{cite}

\usepackage{hyperref}

\usepackage{algorithm}

\usepackage{algorithmic}

\begin{document}

\title{[Paper Title]}

\author{[Authors]}

\maketitle

\begin{abstract}

[Complete abstract 200-300 words]

\end{abstract}

\section{Introduction}

[Complete introduction with full paragraphs...]

\section{Related Work}

[Complete related work review...]

\section{Methodology}

[Complete methodology section...]

\section{Experiments and Results}

[Complete experimental section...]

\section{Conclusion}

[Complete conclusion...]

\begin{thebibliography}{99}

[Complete reference list...]

\end{thebibliography}

\end{document}
```

### If Skipping:

**Reason**: [User provided outline / Existing .tex file exists]

```markdown
SKIPPED
```

**Important**:

- Use ` ```path ` to specify the file name

- Use ` ```latex ` to specify the LaTeX content

- The orchestrator will parse this markdown and save the file

- Do NOT include any file operations in your response"""

    def __init__(self, openai_service: OpenAIService):
        self.openai_service = openai_service
    
    def _parse_markdown_output(self, response: str) -> Tuple[Optional[str], Optional[str], bool]:
        """
        解析 Agent 输出的 markdown 格式，提取文件名和内容
        
        Args:
            response: Agent 的原始响应
            
        Returns:
            (file_name, file_content, is_skipped) 或 (None, None, False) 如果解析失败
            is_skipped: True 表示跳过生成，False 表示正常生成
        """
        try:
            # 检查是否跳过生成
            if "SKIPPED" in response.upper() or "SKIP" in response.upper():
                logger.info("Agent skipped LaTeX paper generation")
                return None, response, True
            
            # 匹配 ```path ... ``` 块（更宽松的匹配，支持多种格式）
            path_pattern = r'```path\s*\n?(.*?)\n?```'
            path_match = re.search(path_pattern, response, re.DOTALL)
            
            # 匹配 ```latex ... ``` 块（更宽松的匹配）
            latex_pattern = r'```latex\s*\n?(.*?)\n?```'
            latex_match = re.search(latex_pattern, response, re.DOTALL)
            
            if path_match and latex_match:
                file_name = path_match.group(1).strip()
                file_content = latex_match.group(1).strip()
                
                # 验证文件名格式
                if not file_name or not file_name.endswith('.tex'):
                    logger.warning(f"Invalid file name format: {file_name}")
                
                return file_name, file_content, False
            else:
                logger.warning("Failed to parse markdown output: missing path or latex block")
                if not path_match:
                    logger.warning("Missing ```path block")
                if not latex_match:
                    logger.warning("Missing ```latex block")
                return None, None, False
                
        except Exception as e:
            logger.error(f"Error parsing markdown output: {str(e)}")
            return None, None, False
    
    async def _generate_latex_paper_attempt(
        self,
        paper_overview: str,
        user_document: Optional[str],
        user_info: Optional[str],
        temperature: Optional[float],
        max_tokens: int,
        model: Optional[str],
        attempt_number: int = 1
    ) -> Optional[Dict[str, Any]]:
        """
        单次生成尝试（内部方法，用于重试）
        
        Args:
            paper_overview: 从 Paper Overview Agent 得到的文本内容
            user_document: 从步骤0得到的合并文档内容
            user_info: 用户提供的额外信息
            temperature: 温度参数（如果为 None，使用默认值 0.7）
            max_tokens: 最大token数
            model: 模型名称
            attempt_number: 当前尝试次数
            
        Returns:
            成功时返回结果字典，失败时返回 None
        """
        # 如果 temperature 为 None，使用默认值 0.7
        if temperature is None:
            temperature = 0.7
        
        # 重试时降低 temperature 以提高稳定性
        adjusted_temperature = max(0.3, temperature - (attempt_number - 1) * 0.1)
        
        # 构建用户消息
        user_content = f"""Please generate a complete LaTeX paper based on the following information:

## Paper Overview (from previous agent):
{paper_overview}

"""
        
        if user_document:
            user_content += f"""
## Original User Document (from step 0):
{user_document}

"""
        
        if user_info:
            user_content += f"""
## Additional User Information:
{user_info}

"""
        
        user_content += """
Please generate a complete LaTeX paper with all required sections filled with detailed content."""
        
        # 重试时增强格式要求提示
        if attempt_number > 1:
            user_content += "\n\n⚠️ IMPORTANT: You MUST output in the exact format with ```path and ```latex blocks. Ensure both blocks are present and properly formatted."
        
        # 构建消息
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
        
        # 调用 OpenAI
        raw_response, usage = await self.openai_service.chat_completion(
            messages=messages,
            temperature=adjusted_temperature,
            max_tokens=max_tokens,
            model=model
        )
        
        # 解析输出
        file_name, file_content, is_skipped = self._parse_markdown_output(raw_response)
        
        if is_skipped:
            # 提取跳过原因
            skip_reason_match = re.search(r'Reason[:\s]+(.*?)(?:\n|$)', raw_response, re.IGNORECASE)
            skip_reason = skip_reason_match.group(1).strip() if skip_reason_match else "Unknown reason"
            
            logger.info(f"Agent skipped LaTeX paper generation: {skip_reason}")
            return {
                "file_name": None,
                "file_content": None,
                "raw_response": raw_response,
                "is_skipped": True,
                "skip_reason": skip_reason,
                "usage": usage
            }
        
        if file_name is None or file_content is None:
            logger.warning(f"Attempt {attempt_number}: Failed to parse agent output")
            return None
        
        logger.info(f"LaTeX paper generated successfully on attempt {attempt_number}: {file_name}")
        
        return {
            "file_name": file_name,
            "file_content": file_content,
            "raw_response": raw_response,
            "is_skipped": False,
            "skip_reason": None,
            "usage": usage
        }
    
    async def generate_latex_paper(
        self,
        paper_overview: str,
        user_document: Optional[str] = None,
        user_info: Optional[str] = None,
        has_outline: bool = False,
        has_existing_tex: bool = False,
        temperature: Optional[float] = 0.7,
        max_tokens: int = 16000,
        model: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        生成 LaTeX 论文（带重试机制）
        
        Args:
            paper_overview: 从 Paper Overview Agent 得到的文本内容
            user_document: 从步骤0得到的合并文档内容（combined_document）
            user_info: 用户提供的额外信息
            has_outline: 用户是否提供了论文大纲
            has_existing_tex: 是否存在现有的 .tex 文件
            temperature: 温度参数
            max_tokens: 最大token数
            model: 模型名称
            
        Returns:
            {
                "file_name": str or None,
                "file_content": str or None,
                "raw_response": str,
                "is_skipped": bool,
                "skip_reason": str or None,
                "usage": dict
            }
            
        Raises:
            ValueError: 如果所有重试都失败
        """
        # 检查生成条件（跳过的情况不需要重试）
        if has_outline or has_existing_tex:
            skip_reason = "User provided outline" if has_outline else "Existing .tex file exists"
            logger.info(f"Skipping LaTeX paper generation: {skip_reason}")
            return {
                "file_name": None,
                "file_content": None,
                "raw_response": f"SKIPPED: {skip_reason}",
                "is_skipped": True,
                "skip_reason": skip_reason,
                "usage": {}
            }
        
        def is_parse_failed(result: Optional[Dict[str, Any]]) -> bool:
            """检查解析是否失败（跳过的情况不算失败）"""
            if result is None:
                return True
            # 如果结果表示跳过，不算失败，不重试
            if result.get("is_skipped", False):
                return False
            # 成功解析，不重试
            return False
        
        attempt_number = 1
        last_result = None
        
        try:
            async for attempt in AsyncRetrying(
                stop=stop_after_attempt(3),
                retry=retry_if_result(is_parse_failed),
                wait=wait_exponential(multiplier=1, min=2, max=10),
                before_sleep=before_sleep_log(logger, logging.WARNING)
            ):
                with attempt:
                    last_result = await self._generate_latex_paper_attempt(
                        paper_overview=paper_overview,
                        user_document=user_document,
                        user_info=user_info,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        model=model,
                        attempt_number=attempt_number
                    )
                    attempt_number += 1
                    
                    # 如果跳过，直接返回（不会触发重试，因为 is_parse_failed 返回 False）
                    if last_result and last_result.get("is_skipped", False):
                        return last_result
                    
                    # 如果解析成功，直接返回
                    if last_result is not None:
                        return last_result
                    
                    # 如果解析失败，触发重试
                    raise ValueError("Parse failed, will retry")
        except RetryError:
            # 所有重试都失败
            logger.error(f"Failed to generate LaTeX paper after {attempt_number - 1} attempts")
            raise ValueError("Agent output format is invalid after multiple retries. Expected markdown format with ```path and ```latex blocks.")
        
        # 如果 somehow 到达这里，返回最后的结果
        if last_result is None:
            raise ValueError("Agent output format is invalid. Expected markdown format with ```path and ```latex blocks.")
        return last_result
    
    async def generate_latex_paper_stream(
        self,
        paper_overview: str,
        user_document: Optional[str] = None,
        user_info: Optional[str] = None,
        has_outline: bool = False,
        has_existing_tex: bool = False,
        temperature: Optional[float] = 0.7,
        max_tokens: int = 16000,
        model: Optional[str] = None
    ):
        """
        流式生成 LaTeX 论文（异步生成器函数）
        
        Args:
            paper_overview: 从 Paper Overview Agent 得到的文本内容
            user_document: 从步骤0得到的合并文档内容（combined_document）
            user_info: 用户提供的额外信息
            has_outline: 用户是否提供了论文大纲
            has_existing_tex: 是否存在现有的 .tex 文件
            temperature: 温度参数
            max_tokens: 最大token数
            model: 模型名称
            
        Yields:
            OpenAI 流式响应 chunk
            
        Raises:
            ValueError: 如果跳过生成（在流式模式下，跳过应该通过异常处理）
        """
        # 检查生成条件
        if has_outline or has_existing_tex:
            skip_reason = "User provided outline" if has_outline else "Existing .tex file exists"
            logger.info(f"Skipping LaTeX paper generation (stream mode): {skip_reason}")
            # 在流式模式下，跳过生成应该通过异常或特殊响应处理
            # 这里返回一个包含跳过信息的简单流
            skip_message = f"SKIPPED: {skip_reason}\n```markdown\nSKIPPED\n```"
            # 模拟 OpenAI 流式响应格式
            for char in skip_message:
                yield {
                    "choices": [{
                        "delta": {
                            "content": char
                        }
                    }]
                }
            # 发送完成信号
            yield {
                "choices": [{
                    "finish_reason": "stop",
                    "delta": {}
                }]
            }
            return
        
        # 构建用户消息
        user_content = f"""Please generate a complete LaTeX paper based on the following information:

## Paper Overview (from previous agent):
{paper_overview}

"""
        
        if user_document:
            user_content += f"""
## Original User Document (from step 0):
{user_document}

"""
        
        if user_info:
            user_content += f"""
## Additional User Information:
{user_info}

"""
        
        user_content += """
Please generate a complete LaTeX paper with all required sections filled with detailed content."""
        
        # 构建消息
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
        
        # 调用 OpenAI 流式接口
        # chat_completion_stream 返回异步生成器对象，我们需要 await 它来获取生成器
        stream_generator = await self.openai_service.chat_completion_stream(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            model=model
        )
        
        logger.info("LaTeX paper streaming started")
        # 使用 async for 和 yield 来转发流式响应
        async for chunk in stream_generator:
            yield chunk

