"""
Conclusion Writing Agent - 专门用于撰写学术论文的 Conclusion 部分
基于方法描述、检索到的相关论文和实验结果，生成符合顶级会议标准的 LaTeX Conclusion 章节
"""
import json
import re
from typing import Any, Dict, List, Optional

from tenacity import AsyncRetrying, retry_if_result, stop_after_attempt, wait_exponential

from app.services.openai_service import OpenAIService
from app.utils.logger import logger


class ConclusionWritingAgent:
    """
    Agent responsible for composing the full Conclusion section as LaTeX,
    including summary of SOTA methods, limitations, our method's contributions,
    experimental results summary, overall contributions, and future directions,
    following SCI journal paper standards.
    
    The Conclusion section is written as a SINGLE, CONCISE paragraph (200-300 words)
    with no paragraph breaks, no empty lines, and no bullet points.
    All content flows continuously as one cohesive narrative.
    """

    SYSTEM_PROMPT = """# Role Definition

You are a top-tier AI research writing assistant with NeurIPS/ICLR/ICML/CVPR/ACL-level expertise.

You excel at:
- Summarizing SOTA methods and their characteristics
- Identifying limitations of existing approaches
- Clearly describing the problems the new method solves
- Explaining the proposed method and how it addresses these limitations
- Summarizing experimental results concisely
- Providing overall contributions
- Suggesting future directions
- Writing highly polished academic English
- Following LaTeX formatting conventions

---

# Core Task

Given:
- Methods LaTeX content: The complete LaTeX Methods section from the Methods Writing Agent
- Experiment LaTeX content: The complete LaTeX Experiment section from the Main Results Writing Agent
- innovation_key_info (optional): Structured JSON containing authoritative information about:
  - final_proposal_topic: The method name (use this consistently throughout)
  - final_problem_statement: The problem statement for the opening paragraph
  - final_method_proposal_text: Summary of the method's core approach
  - method_context.research_question: The research question being addressed
  - method_context.problem_gap: The gap in existing approaches
  - module_weaknesses: List of weaknesses in existing modules (use for limitations section)
  - module_innovations: List of improvements made to each module (use for solution section)
  - selected_pipeline.rationale: Why this pipeline combination was chosen

**CRITICAL: If innovation_key_info is provided, use it as the PRIMARY SOURCE** for:
- Method name (use final_proposal_topic consistently)
- Problem statement (use final_problem_statement)
- Research question and problem gap (use method_context fields)
- Limitations of existing approaches (use module_weaknesses - more accurate than extracting from LaTeX)
- How our method addresses limitations (use module_innovations and selected_pipeline.rationale)

Supplement with information extracted from LaTeX sections when needed.

Your job is to automatically write a full Conclusion section by:
1. **PRIORITIZING** structured information from innovation_key_info (if provided) for method name, problem statement, limitations, and innovations
2. Extracting key information from the Methods section (key innovations, architecture details, advantages)
3. Extracting key information from the Experiment section, especially:
   - The overview questions from Experiment section (e.g., "In this section, we demonstrate... by addressing [NUMBER] key questions: (1) [QUESTION 1]? (2) [QUESTION 2]? (3) [QUESTION 3]?")
   - Benchmarks, results, and findings
   - Ablation study results
4. Synthesizing this information into a cohesive Conclusion following the required structure

The Conclusion section MUST be written as a SINGLE, CONCISE paragraph (no paragraph breaks, no empty lines). It should cover these elements in a condensed, flowing narrative:

1. **Method introduction**: "In this work, we present [OUR METHOD NAME], unlike [other methods], our work [key advantages]"
2. **Experimental results**: Briefly summarize key experimental findings and how they address the main research questions
3. **Contributions**: Highlight the main contributions to the field
4. **Future work** (optional, only if space allows): One brief sentence about future directions

Output must be:
- Formal academic tone
- Concise and condensed (aim for 200-300 words total)
- Single paragraph with no breaks
- Free of hype, but authoritative
- Fully self-contained LaTeX form
- Ready to paste into a paper

---

# Output Structure

**CRITICAL: The Conclusion section MUST be written as a SINGLE paragraph with NO paragraph breaks, NO empty lines, and NO bullet points. This is a concise, condensed summary that flows as one continuous narrative.**

You MUST output a single LaTeX block that exactly follows the structure below, **wrapped inside a single ```latex ... ``` fenced code block**, with no extra commentary before or after.

The entire Conclusion must be ONE paragraph only - all content should flow continuously without any line breaks or paragraph separators.

```latex
\\section{Conclusion}

In this work, we present \\textbf{[OUR METHOD NAME]}, a novel [ARCHITECTURE/FRAMEWORK/APPROACH] that [BRIEF DESCRIPTION OF KEY INNOVATION]. Unlike existing methods such as [Method-1], [Method-2], and [Method-3], which [COMMON LIMITATION OR APPROACH], our work [KEY ADVANTAGE 1], [KEY ADVANTAGE 2], and [KEY ADVANTAGE 3], enabling [NEW CAPABILITY] and [FUNDAMENTAL IMPROVEMENT]. Extensive experiments on [BENCHMARK 1], [BENCHMARK 2], and [BENCHMARK 3] demonstrate that [OUR METHOD NAME] [ANSWERS TO EXPERIMENT OVERVIEW QUESTIONS - extract the key questions from the Experiment section overview and answer them concisely], achieving [KEY METRIC IMPROVEMENTS] while maintaining [ADDITIONAL BENEFITS]. Ablation studies validate the effectiveness of [COMPONENT 1], [COMPONENT 2], and [COMPONENT 3] in our design. Overall, this work makes significant contributions to [FIELD] by [CONTRIBUTION 1], [CONTRIBUTION 2], and [CONTRIBUTION 3], establishing [OUR METHOD NAME] as a [POSITIONING STATEMENT, e.g., "state-of-the-art solution" or "promising approach"] for [APPLICATION DOMAIN].
```

---

# Critical Constraints

- **SINGLE paragraph format**: The entire Conclusion section MUST be written as a SINGLE paragraph with NO paragraph breaks, NO empty lines between sentences, and NO bullet points. **DO NOT use bullet points, itemize environments (`\\begin{itemize} ... \\end{itemize}`), enumerate environments (`\\begin{enumerate} ... \\end{enumerate}`), paragraph separators (`\\paragraph{}`), or any line breaks that create multiple paragraphs**. This is a concise, condensed summary that flows as one continuous narrative.
- **Extract from provided sections**: Extract method name, key innovations, benchmarks, and results from the provided Methods and Experiment LaTeX sections. Ground all claims about SOTA methods and limitations based on information in these sections. Use actual method names but **DO NOT include citations** (no \\cite commands).
- **Use provided method name**: Consistently use the provided method name throughout (replace [OUR METHOD NAME]).
- **Realistic experimental claims**: Base experimental performance summary on provided results or reasonable expectations. Avoid exaggeration.
- **Concise single paragraph**: Ensure smooth logical flow: opening (present method, highlight advantages vs. other methods) → extensive experiments (answer Experiment overview questions concisely) → ablation studies → overall contributions → future work (optional), all written as ONE continuous paragraph without any breaks, empty lines, or bullet points. Keep it concise (aim for 200-300 words total).
- **Answer Experiment overview questions**: Extract the key questions from the Experiment section overview (e.g., "In this section, we demonstrate the effectiveness of [YOUR METHOD] by addressing [NUMBER] key questions: (1) [QUESTION 1]? (2) [QUESTION 2]? (3) [QUESTION 3]?") and answer them concisely in the "Extensive experiments" sentence, showing how the experimental results address each question.
- **Formal academic tone**: Maintain confident, precise, non-exaggerated writing style.
- **No placeholders**: Replace all bracketed placeholders with concrete, grounded content.
- **LaTeX formatting**: Use proper LaTeX syntax and formatting conventions, but **DO NOT include any citation commands** (\\cite, \\citep, etc.).
- **Mathematical Equations Format**: All displayed mathematical equations MUST use `\\begin{equation} ... \\end{equation}` environment. NEVER use `$$ ... $$`, `\\[ ... \\]`, or `\\( ... \\)` for displayed equations. Inline math can use `$ ... $` or `\\( ... \\)`, but displayed equations must use `\\begin{equation}` with proper labels (e.g., `\\label{eq:example}`) for cross-referencing.

---

# Tone & Style

- Mirror SOTA conference writing: confident, precise, non-exaggerated
- Use active voice, formal tone, and data-backed claims
- Avoid hype and marketing language
- Present contributions as technically meaningful achievements
- Future work should be specific and actionable, not vague

---

# Output Format

- Output the complete LaTeX Conclusion section wrapped in a single ```latex ... ``` fenced code block
- Do not include any other text outside the code block
"""

    def __init__(self, openai_service: OpenAIService):
        """
        Initialize the Conclusion Writing Agent.
        
        Args:
            openai_service: OpenAI service instance for API calls
        """
        self.openai_service = openai_service

    @staticmethod
    def _extract_key_info(innovation_json: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract only the key information needed for Conclusion section generation.
        
        Args:
            innovation_json: Full JSON from InnovationSynthesisAgent
            
        Returns:
            Simplified JSON containing only essential fields for Conclusion section
        """
        key_info = {}
        
        # 1. Core method information (high priority)
        if "final_proposal_topic" in innovation_json:
            key_info["final_proposal_topic"] = innovation_json["final_proposal_topic"]
        if "final_problem_statement" in innovation_json:
            key_info["final_problem_statement"] = innovation_json["final_problem_statement"]
        if "final_method_proposal_text" in innovation_json:
            key_info["final_method_proposal_text"] = innovation_json["final_method_proposal_text"]
        
        # 2. Research context and problem gap (high priority)
        if "method_context" in innovation_json:
            method_context = innovation_json["method_context"]
            key_info["method_context"] = {
                "research_question": method_context.get("research_question", ""),
                "problem_gap": method_context.get("problem_gap", ""),
            }
        
        # 3. Limitations of existing approaches (high priority)
        # 4. Method innovations (medium priority)
        # Extract weaknesses and improvements from each module in a single pass
        if "module_blueprints" in innovation_json:
            module_blueprints = innovation_json["module_blueprints"]
            if "modules" in module_blueprints:
                key_info["module_weaknesses"] = []
                key_info["module_innovations"] = []
                for module in module_blueprints["modules"]:
                    module_id = module.get("id", "")
                    
                    # Extract weaknesses (for limitations section)
                    weaknesses = module.get("weaknesses", [])
                    if weaknesses:
                        module_name = module.get("improvement", {}).get("name", f"Module {module_id}")
                        key_info["module_weaknesses"].append({
                            "module_id": module_id,
                            "module_name": module_name,
                            "weaknesses": weaknesses,
                        })
                    
                    # Extract improvements (for solution section)
                    improvement = module.get("improvement", {})
                    if improvement:
                        key_info["module_innovations"].append({
                            "module_id": module_id,
                            "improved_name": improvement.get("name", f"Module {module_id}*"),
                            "design_changes": improvement.get("design_changes", []),
                            "workflow_change": improvement.get("workflow_change", ""),
                        })
        
        # Extract selected pipeline rationale
        if "integration_strategy" in innovation_json:
            integration = innovation_json["integration_strategy"]
            if "selected_pipeline" in integration:
                selected = integration["selected_pipeline"]
                key_info["selected_pipeline"] = {
                    "pipeline": selected.get("pipeline", ""),
                    "rationale": selected.get("rationale", ""),
                }
        
        return key_info

    @staticmethod
    def _extract_method_name_from_latex(methods_latex: str) -> Optional[str]:
        """
        Extract method name from Methods LaTeX content.
        
        Args:
            methods_latex: LaTeX content of Methods section
            
        Returns:
            Extracted method name, or None if not found
        """
        # Look for method name in Overview section or section title
        # Common patterns: "we propose", "we introduce", "we present", etc.
        patterns = [
            r'we propose (?:a |an )?\\textbf\{([^}]+)\}',
            r'we introduce (?:a |an )?\\textbf\{([^}]+)\}',
            r'we present (?:a |an )?\\textbf\{([^}]+)\}',
            r'\\textbf\{([^}]+)\} (?:is|represents|denotes) (?:a |an )?(?:novel|new|proposed)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, methods_latex, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        
        # Fallback: look for section title or first bold text
        bold_match = re.search(r'\\textbf\{([^}]+)\}', methods_latex)
        if bold_match:
            return bold_match.group(1).strip()
        
        return None

    def _build_user_prompt(
        self,
        methods_latex_content: str,
        experiment_latex_content: str,
        innovation_json: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Build the user prompt for the LLM.
        
        Args:
            methods_latex_content: Complete LaTeX Methods section content
            experiment_latex_content: Complete LaTeX Experiment section content
            innovation_json: Optional innovation synthesis JSON for structured information
            
        Returns:
            Formatted user prompt string
        """
        if not methods_latex_content or not methods_latex_content.strip():
            raise ValueError("methods_latex_content is required and cannot be empty.")
        if not experiment_latex_content or not experiment_latex_content.strip():
            raise ValueError("experiment_latex_content is required and cannot be empty.")

        payload: Dict[str, Any] = {
            "methods_section": methods_latex_content.strip(),
            "experiment_section": experiment_latex_content.strip(),
        }
        
        # Add innovation JSON key info if provided
        if innovation_json:
            key_info = self._extract_key_info(innovation_json)
            if key_info:
                payload["innovation_key_info"] = key_info

        payload_text = json.dumps(payload, ensure_ascii=False, indent=2)
        
        reminder = """Remember:
- **CRITICAL: SINGLE paragraph format** - The entire Conclusion section MUST be written as a SINGLE paragraph with NO paragraph breaks, NO empty lines, and NO bullet points. **DO NOT use bullet points, itemize environments (`\\begin{itemize} ... \\end{itemize}`), enumerate environments (`\\begin{enumerate} ... \\end{enumerate}`), paragraph separators (`\\paragraph{}`), or any line breaks that create multiple paragraphs**. Keep it concise (aim for 200-300 words total).
- **CRITICAL: Concise Conclusion structure** - Follow this condensed structure in ONE paragraph: (1) Opening: "In this work, we present [OUR METHOD NAME], unlike [other methods], our work [key advantages]"; (2) Extensive experiments: Extract the key questions from Experiment section overview and answer them concisely; (3) Ablation studies: Briefly mention key ablation findings; (4) Overall contributions: Highlight the main contributions. All content must flow continuously without breaks.
- **PRIORITY: Use structured information from innovation_key_info if provided** - The innovation_key_info contains authoritative structured data about the method name, problem statement, research question, limitations, and innovations. Use this information as the primary source, and supplement with information extracted from LaTeX sections.
- Extract the method name from innovation_key_info.final_proposal_topic (if available) or from the Methods section, and use it consistently throughout (replace [OUR METHOD NAME]).
- Use innovation_key_info.final_problem_statement for the problem statement.
- Use innovation_key_info.method_context.research_question and problem_gap for research context.
- Use innovation_key_info.module_weaknesses for limitations of existing approaches - these are more accurate than extracting from LaTeX.
- Use innovation_key_info.module_innovations and selected_pipeline.rationale for describing how our method addresses limitations and highlighting advantages.
- Extract key method innovations, components, and architecture from the Methods section.
- **CRITICAL: Extract Experiment overview questions** - From the Experiment section, find the overview paragraph that states "In this section, we demonstrate... by addressing [NUMBER] key questions: (1) [QUESTION 1]? (2) [QUESTION 2]? (3) [QUESTION 3]?". Extract these questions and answer them concisely in the "Extensive experiments" sentence, showing how experimental results address each question.
- Extract benchmarks, results, ablation findings, and findings from the Experiment section.
- Ground all claims about SOTA methods and limitations based on information in innovation_key_info (if provided) or the Methods and Experiment sections.
- **DO NOT include any citations** (no \\cite, \\citep, or any citation commands).
- Base experimental performance summary on the actual results reported in the Experiment section.
- Write in formal academic tone, confident but not exaggerated.
- Replace all bracketed placeholders with concrete, grounded content extracted from the provided sections.
- **CRITICAL: Mathematical Equations Format**: All displayed mathematical equations MUST use `\\begin{equation} ... \\end{equation}` environment. NEVER use `$$ ... $$`, `\\[ ... \\]`, or `\\( ... \\)` for displayed equations. Inline math can use `$ ... $` or `\\( ... \\)`, but displayed equations must use `\\begin{equation}` with proper labels (e.g., `\\label{eq:example}`) for cross-referencing.
- Future work should be specific and actionable, not vague generalizations, and should be integrated into the continuous narrative flow.
- Output only the LaTeX Conclusion section wrapped in ```latex ... ``` blocks.
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
                    "ConclusionWritingAgent: extracted latex block (length=%d chars)",
                    len(content),
                )
                return content
            
            # Fallback: any fenced code block
            code_block_pattern = r"```\w*\s*\n?(.*?)```"
            code_match = re.search(code_block_pattern, response, re.DOTALL)
            if code_match:
                logger.warning(
                    "ConclusionWritingAgent: no ```latex block found, using generic code block"
                )
                return code_match.group(1).strip()
            
            logger.warning(
                "ConclusionWritingAgent: missing ```latex block in response"
            )
            logger.debug("Full response (truncated):\n%s", response[:1000])
            return None
            
        except Exception as exc:
            logger.warning(
                "ConclusionWritingAgent: failed to extract LaTeX block: %s", exc
            )
            logger.debug("Full response (truncated):\n%s", response[:1000])
            return None

    async def generate_conclusion_section(
        self,
        methods_latex_content: str,
        experiment_latex_content: str,
        *,
        innovation_json: Optional[Dict[str, Any]] = None,
        temperature: float = 0.7,
        max_tokens: int = 6000,
        model: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Generate the Conclusion section based on Methods and Experiment LaTeX sections.
        
        Args:
            methods_latex_content: Complete LaTeX Methods section content (required)
                This should be the content from innovation_synthesis_methods.tex
            experiment_latex_content: Complete LaTeX Experiment section content (required)
                This should be the content from innovation_synthesis_main_results.tex
            innovation_json: Optional innovation synthesis JSON from InnovationSynthesisAgent
                If provided, structured information (method name, problem statement, limitations, 
                innovations) will be extracted and used as the primary source for these fields.
                This ensures consistency and accuracy in the Conclusion section.
            temperature: Temperature for generation (default: 0.7)
            max_tokens: Maximum tokens for generation (default: 6000)
            model: Model name (optional, uses service default)
            
        Returns:
            Dictionary containing:
                - content: The generated LaTeX Conclusion section
                - raw_response: Full raw response from the model
                - usage: Token usage statistics
                
        Raises:
            ValueError: If required inputs are missing or if generation fails after retries
        """
        
        user_content = self._build_user_prompt(
            methods_latex_content=methods_latex_content,
            experiment_latex_content=experiment_latex_content,
            innovation_json=innovation_json,
        )

        async def _attempt(attempt_number: int) -> Optional[Dict[str, Any]]:
            messages = [
                {"role": "system", "content": self.SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ]
            
            logger.info(
                "ConclusionWritingAgent attempt %d (payload chars=%d)",
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
                    "ConclusionWritingAgent: empty response from chat_completion"
                )
                return None

            latex_content = self._extract_latex_block(response)
            if latex_content is None or "\\section{Conclusion}" not in latex_content:
                logger.warning(
                    "ConclusionWritingAgent: failed to extract valid LaTeX Conclusion section"
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
                "ConclusionWritingAgent failed to produce a valid response after retries."
            )

        return result


__all__ = ["ConclusionWritingAgent"]

