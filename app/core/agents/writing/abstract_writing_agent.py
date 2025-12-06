"""
Abstract Writing Agent - 专门用于撰写学术论文的 Abstract 部分
基于 Introduction、Main Results/Experiment 和 Conclusion 部分的 LaTeX 内容，
生成符合顶级会议/期刊标准的 LaTeX Abstract
"""
import json
import re
from typing import Any, Dict, Optional

from tenacity import AsyncRetrying, retry_if_result, stop_after_attempt, wait_exponential

from app.services.openai_service import OpenAIService
from app.utils.logger import logger


class AbstractWritingAgent:
    """
    Agent responsible for composing the Abstract section as LaTeX.
    
    The Abstract is a concise, single-paragraph summary that includes:
    - Background on current methods
    - Identified limitations
    - Motivation and description of our method
    - Summary of experimental results
    - Overall statement of contributions and impact
    - Future work suggestions
    
    The output is a SINGLE, CONCISE paragraph (typically 150-250 words)
    with no paragraph breaks, following academic journal/conference standards.
    """

    SYSTEM_PROMPT = """# Role Definition

You are a top-tier AI research writing assistant with NeurIPS/ICLR/ICML/CVPR/ACL-level expertise.

You excel at:
- Synthesizing scientific background from Introduction sections
- Summarizing SOTA methods and their limitations
- Identifying gaps in prior work and motivating a new method
- Summarizing experimental results concisely
- Highlighting contributions and impact
- Suggesting future work directions
- Writing highly polished, concise academic English
- Following LaTeX formatting conventions

---

# Core Task

Given:
- Introduction LaTeX content: The complete LaTeX Introduction section containing:
  - Background on the field and SOTA methods
  - Limitations of existing approaches
  - Motivation for the new method
  - High-level overview of the proposed method
  - Summary of contributions (in itemize format)
  
- Main Results/Experiment LaTeX content: The complete LaTeX Experiment section containing:
  - Overview questions and experimental setup
  - Benchmarks and datasets used
  - Experimental results and findings
  - Ablation study results
  - Performance improvements and metrics
  
- Conclusion LaTeX content: The complete LaTeX Conclusion section containing:
  - Summary of the method and its advantages
  - Overall contributions to the field
  - Future work directions (if mentioned)

Your job is to synthesize this information into a cohesive Abstract that follows the required structure.

The Abstract section MUST be written as a SINGLE, CONCISE paragraph (no paragraph breaks, no empty lines). It should cover these elements in a condensed, flowing narrative:

1. **Background on current methods**: Briefly introduce the field and what SOTA methods do
2. **Identified limitations**: Concise statement of key limitations in existing approaches
3. **Motivation and description of our method**: Present our method as a response to limitations, with brief high-level description
4. **Summary of experimental results**: Concise summary of key experimental findings, benchmarks, and improvements
5. **Overall statement of contributions and impact**: Highlight main contributions to the field
6. **Future work suggestions**: One brief sentence about future directions (if space allows)

Output must be:
- Formal academic tone
- Concise and condensed (aim for 150-250 words total)
- Single paragraph with no breaks
- Free of hype, but authoritative
- Fully self-contained LaTeX form
- Ready to paste into a paper

---

# Output Structure

**CRITICAL: The Abstract section MUST be written as a SINGLE paragraph with NO paragraph breaks, NO empty lines, and NO bullet points. This is a concise, condensed summary that flows as one continuous narrative.**

You MUST output a single LaTeX block that exactly follows the structure below, **wrapped inside a single ```latex ... ``` fenced code block**, with no extra commentary before or after.

The entire Abstract must be ONE paragraph only - all content should flow continuously without any line breaks or paragraph separators.

```latex
\\begin{abstract}
Recent advances in [FIELD] have led to powerful methods capable of [KEY ACHIEVEMENTS]. State-of-the-art approaches, including [Method-1], [Method-2], and [Method-3], typically [COMMON APPROACH]. Despite these advances, existing methods face several fundamental challenges: (1) [LIMITATION 1]; (2) [LIMITATION 2]; and (3) [LIMITATION 3]. To address these limitations, we introduce \\textbf{[OUR METHOD NAME]}, a novel [ARCHITECTURE/FRAMEWORK] that [BRIEF METHOD DESCRIPTION]. Our approach [KEY INNOVATION 1], [KEY INNOVATION 2], and [KEY INNOVATION 3], enabling [NEW CAPABILITY] and [FUNDAMENTAL IMPROVEMENT]. Extensive experiments on [BENCHMARK 1], [BENCHMARK 2], and [BENCHMARK 3] demonstrate that [OUR METHOD NAME] [KEY RESULTS], achieving [METRIC IMPROVEMENTS] while maintaining [ADDITIONAL BENEFITS]. Our work makes significant contributions to [FIELD] by [CONTRIBUTION 1], [CONTRIBUTION 2], and [CONTRIBUTION 3], establishing [OUR METHOD NAME] as a [POSITIONING STATEMENT] for [APPLICATION DOMAIN]. [OPTIONAL FUTURE WORK: Future work will explore [SPECIFIC DIRECTION].]
\\end{abstract}
```

---

# Critical Constraints

- **SINGLE paragraph format**: The entire Abstract section MUST be written as a SINGLE paragraph with NO paragraph breaks, NO empty lines between sentences, and NO bullet points. **DO NOT use bullet points, itemize environments (`\\begin{itemize} ... \\end{itemize}`), enumerate environments (`\\begin{enumerate} ... \\end{enumerate}`), paragraph separators (`\\paragraph{}`), or any line breaks that create multiple paragraphs**. This is a concise, condensed summary that flows as one continuous narrative.

- **Extract from provided sections**: 
  - Extract background and SOTA methods from Introduction section
  - Extract limitations from Introduction section
  - Extract method motivation and description from Introduction section
  - Extract experimental results, benchmarks, and findings from Main Results/Experiment section
  - Extract contributions from Introduction (itemize format) or Conclusion section
  - Extract future work from Conclusion section (if available)
  - Use actual method names but **DO NOT include citations** (no \\cite commands).

- **Use provided method name**: Extract the method name from Introduction or Conclusion section and use it consistently throughout (replace [OUR METHOD NAME]). Common patterns: look for "we introduce", "we propose", "we present" followed by \\textbf{...}.

- **Realistic experimental claims**: Base experimental performance summary on the actual results reported in the Main Results/Experiment section. Avoid exaggeration.

- **Concise single paragraph**: Ensure smooth logical flow: Background → Limitations → Motivation/Method → Results → Contributions → Future work, all written as ONE continuous paragraph without any breaks, empty lines, or bullet points. Keep it concise (aim for 150-250 words total).

- **Formal academic tone**: Maintain confident, precise, non-exaggerated writing style.

- **No placeholders**: Replace all bracketed placeholders with concrete, grounded content extracted from the provided sections.

- **LaTeX formatting**: 
  - Use proper LaTeX syntax: `\\begin{abstract} ... \\end{abstract}`
  - **DO NOT include any citation commands** (\\cite, \\citep, etc.)
  - Use `\\textbf{...}` for method names and key terms

- **Mathematical Equations Format**: 
  - Generally avoid equations in Abstract unless absolutely essential
  - If equations are necessary, use inline math `$ ... $` or `\\( ... \\)`
  - Avoid displayed equations (`\\begin{equation} ... \\end{equation}`) in Abstract

---

# Tone & Style

- Mirror SOTA conference/journal writing: confident, precise, non-exaggerated
- Use active voice, formal tone, and data-backed claims
- Avoid hype and marketing language
- Present contributions as technically meaningful achievements
- Future work should be specific and actionable, not vague generalizations

---

# Output Format

- Output the complete LaTeX Abstract section wrapped in a single ```latex ... ``` fenced code block
- Do not include any other text outside the code block
"""

    def __init__(self, openai_service: OpenAIService):
        """
        Initialize the Abstract Writing Agent.
        
        Args:
            openai_service: OpenAI service instance for API calls
        """
        self.openai_service = openai_service

    @staticmethod
    def _extract_method_name_from_latex(latex_content: str) -> Optional[str]:
        """
        Extract method name from LaTeX content.
        
        Args:
            latex_content: LaTeX content (Introduction, Conclusion, etc.)
            
        Returns:
            Extracted method name, or None if not found
        """
        # Look for method name in common patterns
        patterns = [
            r'we propose (?:a |an )?\\textbf\{([^}]+)\}',
            r'we introduce (?:a |an )?\\textbf\{([^}]+)\}',
            r'we present (?:a |an )?\\textbf\{([^}]+)\}',
            r'\\textbf\{([^}]+)\} (?:is|represents|denotes) (?:a |an )?(?:novel|new|proposed)',
            r'In this work, we present \\textbf\{([^}]+)\}',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, latex_content, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        
        # Fallback: look for first bold text that appears after "we" statements
        bold_match = re.search(r'we (?:propose|introduce|present).*?\\textbf\{([^}]+)\}', latex_content, re.IGNORECASE | re.DOTALL)
        if bold_match:
            return bold_match.group(1).strip()
        
        return None

    def _build_user_prompt(
        self,
        introduction_latex_content: str,
        main_results_latex_content: str,
        conclusion_latex_content: str,
    ) -> str:
        """
        Build the user prompt for the LLM.
        
        Args:
            introduction_latex_content: Complete LaTeX Introduction section content (required)
            main_results_latex_content: Complete LaTeX Main Results/Experiment section content (required)
            conclusion_latex_content: Complete LaTeX Conclusion section content (required)
            
        Returns:
            Formatted user prompt string
        """
        if not introduction_latex_content or not introduction_latex_content.strip():
            raise ValueError("introduction_latex_content is required and cannot be empty.")
        if not main_results_latex_content or not main_results_latex_content.strip():
            raise ValueError("main_results_latex_content is required and cannot be empty.")
        if not conclusion_latex_content or not conclusion_latex_content.strip():
            raise ValueError("conclusion_latex_content is required and cannot be empty.")

        # Truncate very long sections to avoid token limits (keep first 6000 chars of each)
        intro_preview = introduction_latex_content[:6000] if len(introduction_latex_content) > 6000 else introduction_latex_content
        results_preview = main_results_latex_content[:6000] if len(main_results_latex_content) > 6000 else main_results_latex_content
        conclusion_preview = conclusion_latex_content[:6000] if len(conclusion_latex_content) > 6000 else conclusion_latex_content

        payload: Dict[str, Any] = {
            "introduction_section": intro_preview.strip(),
            "main_results_section": results_preview.strip(),
            "conclusion_section": conclusion_preview.strip(),
        }
        
        if len(introduction_latex_content) > 6000:
            logger.info("AbstractWritingAgent: truncated introduction from %d to 6000 chars", len(introduction_latex_content))
        if len(main_results_latex_content) > 6000:
            logger.info("AbstractWritingAgent: truncated main_results from %d to 6000 chars", len(main_results_latex_content))
        if len(conclusion_latex_content) > 6000:
            logger.info("AbstractWritingAgent: truncated conclusion from %d to 6000 chars", len(conclusion_latex_content))

        payload_text = json.dumps(payload, ensure_ascii=False, indent=2)
        
        reminder = """Remember:
- **CRITICAL: SINGLE paragraph format** - The entire Abstract section MUST be written as a SINGLE paragraph with NO paragraph breaks, NO empty lines, and NO bullet points. **DO NOT use bullet points, itemize environments (`\\begin{itemize} ... \\end{itemize}`), enumerate environments (`\\begin{enumerate} ... \\end{enumerate}`), paragraph separators (`\\paragraph{}`), or any line breaks that create multiple paragraphs**. Keep it concise (aim for 150-250 words total).

- **CRITICAL: Abstract structure** - Follow this condensed structure in ONE paragraph: (1) Background: Briefly introduce the field and SOTA methods; (2) Limitations: Concise statement of key limitations; (3) Motivation/Method: Present our method as a response, with brief description; (4) Results: Summarize key experimental findings, benchmarks, and improvements; (5) Contributions: Highlight main contributions; (6) Future work (optional): One brief sentence. All content must flow continuously without breaks.

- Extract the method name from Introduction or Conclusion section (look for "we introduce", "we propose", "we present" followed by \\textbf{...}), and use it consistently throughout (replace [OUR METHOD NAME]).

- Extract background and SOTA methods from Introduction section.

- Extract limitations from Introduction section (look for "Despite these advances", "However", or limitations paragraphs).

- Extract method motivation and high-level description from Introduction section.

- Extract experimental results, benchmarks, datasets, and key findings from Main Results/Experiment section. Look for the overview questions and how they are answered.

- Extract contributions from Introduction section (itemize format under "Contributions" paragraph) or Conclusion section.

- Extract future work from Conclusion section (if mentioned).

- **DO NOT include any citations** (no \\cite, \\citep, or any citation commands).

- Base experimental performance summary on the actual results reported in the Main Results/Experiment section.

- Write in formal academic tone, confident but not exaggerated.

- Replace all bracketed placeholders with concrete, grounded content extracted from the provided sections.

- Output only the LaTeX Abstract section wrapped in ```latex ... ``` blocks using `\\begin{abstract} ... \\end{abstract}`.
"""
        
        return f"{payload_text}\n\n{reminder}"

    @staticmethod
    def _extract_latex_block(response: str) -> Optional[str]:
        """
        Extract LaTeX content from response wrapped in ```latex ... ``` blocks.
        
        This mirrors the behavior of other WritingAgents
        so that downstream code can rely on receiving a clean LaTeX snippet without Markdown fences.
        
        Args:
            response: Raw response from the model
            
        Returns:
            Extracted LaTeX content, or None if extraction fails
        """
        try:
            # Match ```latex ... ``` blocks
            latex_pattern = r"```latex\s*\n?(.*?)\n?```"
            match = re.search(latex_pattern, response, re.DOTALL)
            
            if match:
                content = match.group(1).strip()
                logger.debug(
                    "AbstractWritingAgent: extracted latex block (length=%d chars)",
                    len(content),
                )
                return content
            
            # Fallback: any fenced code block
            code_block_pattern = r"```\w*\s*\n?(.*?)```"
            code_match = re.search(code_block_pattern, response, re.DOTALL)
            if code_match:
                logger.warning(
                    "AbstractWritingAgent: no ```latex block found, using generic code block"
                )
                return code_match.group(1).strip()
            
            logger.warning(
                "AbstractWritingAgent: missing ```latex block in response"
            )
            logger.debug("Full response (truncated):\n%s", response[:1000])
            return None
            
        except Exception as exc:
            logger.warning(
                "AbstractWritingAgent: failed to extract LaTeX block: %s", exc
            )
            logger.debug("Full response (truncated):\n%s", response[:1000])
            return None

    async def generate_abstract_section(
        self,
        introduction_latex_content: str,
        main_results_latex_content: str,
        conclusion_latex_content: str,
        *,
        temperature: float = 0.7,
        max_tokens: int = 2000,
        model: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Generate the Abstract section based on Introduction, Main Results, and Conclusion LaTeX sections.
        
        Args:
            introduction_latex_content: Complete LaTeX Introduction section content (required)
                This should contain background, limitations, motivation, method overview, and contributions
            main_results_latex_content: Complete LaTeX Main Results/Experiment section content (required)
                This should contain experimental setup, benchmarks, results, and findings
            conclusion_latex_content: Complete LaTeX Conclusion section content (required)
                This should contain summary of contributions and future work
            temperature: Temperature for generation (default: 0.7)
            max_tokens: Maximum tokens for generation (default: 2000, sufficient for concise abstract)
            model: Model name (optional, uses service default)
            
        Returns:
            Dictionary containing:
                - content: The generated LaTeX Abstract section
                - raw_response: Full raw response from the model
                - usage: Token usage statistics
                
        Raises:
            ValueError: If required inputs are missing or if generation fails after retries
        """
        
        user_content = self._build_user_prompt(
            introduction_latex_content=introduction_latex_content,
            main_results_latex_content=main_results_latex_content,
            conclusion_latex_content=conclusion_latex_content,
        )

        async def _attempt(attempt_number: int) -> Optional[Dict[str, Any]]:
            messages = [
                {"role": "system", "content": self.SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ]
            
            logger.info(
                "AbstractWritingAgent attempt %d (payload chars=%d)",
                attempt_number,
                len(user_content),
            )
            
            # Adjust temperature for retries (more deterministic)
            adjusted_temperature = max(
                0.3, temperature - 0.05 * (attempt_number - 1)
            )
            
            response, usage = await self.openai_service.chat_completion(
                messages=messages,
                temperature=adjusted_temperature,
                max_tokens=max_tokens,
                model=model,
            )

            if not response:
                logger.warning(
                    "AbstractWritingAgent: empty response from chat_completion"
                )
                return None

            latex_content = self._extract_latex_block(response)
            if latex_content is None or "\\begin{abstract}" not in latex_content:
                logger.warning(
                    "AbstractWritingAgent: failed to extract valid LaTeX Abstract section"
                )
                return None

            return {
                "content": latex_content,
                "raw_response": response,
                "usage": usage,
            }

        def _is_failure(result: Optional[Dict[str, Any]]) -> bool:
            return result is None

        result: Optional[Dict[str, Any]] = None
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(3),
            retry=retry_if_result(_is_failure),
            wait=wait_exponential(multiplier=1, min=1, max=4),
        ):
            with attempt:
                attempt_number = attempt.retry_state.attempt_number
                result = await _attempt(attempt_number)
                if result is not None:
                    break

        if result is None:
            raise ValueError(
                "AbstractWritingAgent failed to produce a valid response after retries."
            )

        return result


__all__ = ["AbstractWritingAgent"]

