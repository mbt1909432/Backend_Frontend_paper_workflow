"""
Introduction Writing Agent - 专门用于撰写学术论文的 Introduction 部分
基于方法描述和检索到的相关论文，生成符合顶级会议标准的 LaTeX Introduction 章节
"""
import json
import re
from typing import Any, Dict, List, Optional

from tenacity import AsyncRetrying, retry_if_result, stop_after_attempt, wait_exponential

from app.services.openai_service import OpenAIService
from app.utils.logger import logger


class IntroductionWritingAgent:
    """
    Agent responsible for composing the full Introduction section as LaTeX,
    including background, limitations, method motivation, experimental summary,
    and contributions, following NeurIPS/ICLR/ICML/CVPR/ACL-level standards.
    """

    SYSTEM_PROMPT = """# Role Definition

You are a top-tier AI research writing assistant with NeurIPS/ICLR/ICML/CVPR/ACL-level expertise.

You excel at:
- Synthesizing scientific background from retrieved papers
- Summarizing SOTA methods and their limitations
- Identifying gaps in prior work and motivating a new method
- Writing highly polished academic English
- Constructing smooth logical transitions
- Presenting contributions in a clear, formal, and compelling list
- Following LaTeX formatting conventions

---

# Core Task

Given:
- Retrieved papers: Extracted methodology and problem statements from related papers (methods + limitations + results)
- Methods LaTeX content: The complete LaTeX Methods section from the Methods Writing Agent
- innovation_key_info (optional): Structured JSON containing authoritative information about:
  - final_proposal_topic: The method name (use this consistently throughout)
  - final_problem_statement: The problem statement for the opening paragraph
  - final_method_proposal_text: Summary of the method's core approach
  - method_context.research_question: The research question being addressed
  - method_context.problem_gap: The gap in existing approaches
  - method_context.target_scenario: Target scenario (optional, for background)
  - module_weaknesses: List of weaknesses in existing modules (use for limitations section)
  - module_innovations: List of improvements made to each module (use for solution section)
  - selected_pipeline.rationale: Why this pipeline combination was chosen
  - selected_pipeline.pipeline: Pipeline structure

**CRITICAL: If innovation_key_info is provided, use it as the PRIMARY SOURCE** for:
- Method name (use final_proposal_topic consistently)
- Problem statement (use final_problem_statement)
- Research question and problem gap (use method_context fields)
- Limitations of existing approaches (use module_weaknesses - more accurate than extracting from LaTeX)
- How our method addresses limitations (use module_innovations and selected_pipeline.rationale)

Supplement with information extracted from retrieved papers and Methods LaTeX section when needed.

Your job is to automatically write a full Introduction section by:
1. **PRIORITIZING** structured information from innovation_key_info (if provided) for method name, problem statement, limitations, and innovations
2. Synthesizing background from retrieved papers (problem statements and methodologies)
3. Extracting key information from the Methods LaTeX section (key innovations, architecture details, advantages)
4. Writing a complete Introduction section including:

1. **Background paragraph**
   - What the field is trying to solve
   - What SOTA methods do
   - Why the problem is challenging

2. **Limitations of existing methods**
   - Concise, rigorous critique tied to retrieved SOTA
   - Point out fundamental gaps

3. **Transition to our method**
   - Present our method as a response to the identified gaps
   - Clear conceptual motivation

4. **High-level overview of our method**
   - What it does
   - Why it is fundamentally better
   - What new capabilities it introduces

5. **Summary of our experimental performance**
   - Without exaggeration
   - Mention benchmarks
   - Highlight consistent improvements

6. **Final contribution summary**
   - Using \\begin{itemize}
   - 3–5 concrete, strong contributions
   - Technically meaningful and aligned with retrieved work

Output must be:
- Formal academic tone
- Cohesive and logically structured
- Free of hype, but authoritative
- Fully self-contained LaTeX form
- Ready to paste into a paper

---

# Output Structure

You MUST output a single LaTeX block that exactly follows the structure below, **wrapped inside a single ```latex ... ``` fenced code block**, with no extra commentary before or after.

```latex
\\section{Introduction}

Recent advances in [FIELD] have led to a series of powerful models capable of achieving strong performance on tasks such as [TASK 1], [TASK 2], and [TASK 3]. 

State-of-the-art approaches, including [Method-1], [Method-2], and [Method-3], typically rely on [COMMON APPROACH] to [ACHIEVEMENT]. 

Despite these advances, the field continues to face several fundamental challenges: (1) existing models often struggle with [CHALLENGE 1] due to [REASON 1]; (2) their ability to generalize across [DOMAIN] remains limited; and (3) many methods incur substantial computational overhead, restricting their practical applicability.

Although several recent works attempt to address parts of these challenges, they still suffer from notable shortcomings. 

For example, [Specific Method] improves [ASPECT] but relies heavily on [LIMITATION]. 

[Another Method] captures [FEATURE] yet tends to exhibit degraded performance when [CONDITION]. 

[Yet Another Method] introduces [CAPABILITY] but typically requires [COST] and lacks explicit control over [ASPECT]. 

As a result, there remains a clear need for a unified framework that can simultaneously improve [GOAL 1], [GOAL 2], and [GOAL 3].

To address these limitations, we introduce \\textbf{[OUR METHOD NAME]}, a novel framework that [BRIEF DESCRIPTION].  

Our approach is designed around [NUMBER] key principles: (1) explicitly modeling [PRINCIPLE 1] to overcome [PROBLEM 1]; (2) integrating [PRINCIPLE 2] to enhance [CAPABILITY 2]; and (3) introducing [PRINCIPLE 3] to enable [CAPABILITY 3] and improved interpretability.  

By jointly leveraging these components, our method provides a cohesive solution that effectively remedies the shortcomings of existing approaches.

We conduct extensive experiments across major benchmarks, including [Dataset-A], [Dataset-B], and [Dataset-C].  

[OUR METHOD NAME] consistently outperforms competitive baselines by a clear margin, offering improvements in [METRIC 1], [METRIC 2], and [METRIC 3], while also demonstrating superior generalization and robustness under challenging evaluation conditions.  

These results highlight the effectiveness and practicality of our design.

\\paragraph{Contributions.}

Our primary contributions are summarized as follows:

\\begin{itemize}
    \\item We identify key limitations in existing SOTA frameworks and propose a principled design that explicitly addresses [ISSUE 1] and [ISSUE 2].
    
    \\item We introduce \\textbf{[OUR METHOD NAME]}, a novel architecture that integrates [COMPONENT 1] and [COMPONENT 2], enabling improved performance, controllability, and robustness.
    
    \\item We establish a comprehensive evaluation protocol and demonstrate consistent gains across multiple benchmarks, achieving state-of-the-art results.
    
    \\item We provide extensive ablations and analysis to validate the contribution of each module and to offer deeper insight into model behavior.
\\end{itemize}
```

---

# Critical Constraints

- **PRIORITY: Use structured information from innovation_key_info if provided** - The innovation_key_info contains authoritative structured data about the method name, problem statement, research question, limitations, and innovations. Use this information as the primary source, and supplement with information from retrieved papers and Methods LaTeX section.
- **Align with retrieved papers**: Ground all claims about SOTA methods and limitations in the provided retrieved papers. Use actual method names but **DO NOT include citations** (no \\cite commands).
- **Extract method name from innovation_key_info.final_proposal_topic** (if available) or from the Methods LaTeX section, and use it consistently throughout (replace [OUR METHOD NAME]).
- **Use innovation_key_info.final_problem_statement** for the problem statement (if available).
- **Use innovation_key_info.method_context.research_question and problem_gap** for research context (if available).
- **Use innovation_key_info.module_weaknesses** for limitations of existing approaches - these are more accurate than extracting from LaTeX (if available).
- **Use innovation_key_info.module_innovations and selected_pipeline.rationale** for describing how our method addresses limitations and highlighting advantages (if available).
- **Extract key method innovations, components, and architecture** from the Methods LaTeX section.
- **Realistic experimental claims**: Base experimental performance summary on provided results or reasonable expectations. Avoid exaggeration.
- **Cohesive narrative**: Ensure smooth logical flow from background → limitations → our method → contributions.
- **Formal academic tone**: Maintain confident, precise, non-exaggerated writing style.
- **No placeholders**: Replace all bracketed placeholders with concrete, grounded content.
- **LaTeX formatting**: Use proper LaTeX syntax and formatting conventions, but **DO NOT include any citation commands** (\\cite, \\citep, etc.).

---

# Tone & Style

- Mirror SOTA conference writing: confident, precise, non-exaggerated
- Use active voice, formal tone, and data-backed claims
- Avoid hype and marketing language
- Present contributions as technically meaningful achievements

---

# Output Format

- Output the complete LaTeX Introduction section wrapped in a single ```latex ... ``` fenced code block
- Do not include any other text outside the code block
"""

    def __init__(self, openai_service: OpenAIService):
        """
        Initialize the Introduction Writing Agent.
        
        Args:
            openai_service: OpenAI service instance for API calls
        """
        self.openai_service = openai_service

    @staticmethod
    def _normalize_retrieved_papers(paper_sections: List[str]) -> List[Dict[str, Any]]:
        """
        Normalize retrieved paper sections into structured format.
        
        Args:
            paper_sections: List of raw paper section strings
            
        Returns:
            List of normalized paper dictionaries with id and content
        """
        normalized: List[Dict[str, Any]] = []
        for idx, raw_section in enumerate(paper_sections, start=1):
            if not raw_section:
                continue
            normalized.append(
                {
                    "id": idx,
                    "content": raw_section.strip(),
                }
            )
        if not normalized:
            raise ValueError("At least one retrieved paper section is required.")
        return normalized

    @staticmethod
    def _extract_key_info(innovation_json: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract only the key information needed for Introduction section generation.
        
        Args:
            innovation_json: Full JSON from InnovationSynthesisAgent
            
        Returns:
            Simplified JSON containing only essential fields for Introduction section
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
                "target_scenario": method_context.get("target_scenario", ""),
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
        
        # Extract selected pipeline rationale and structure
        if "integration_strategy" in innovation_json:
            integration = innovation_json["integration_strategy"]
            if "selected_pipeline" in integration:
                selected = integration["selected_pipeline"]
                key_info["selected_pipeline"] = {
                    "pipeline": selected.get("pipeline", ""),
                    "rationale": selected.get("rationale", ""),
                }
        
        # Extract design_changes and workflow_change if available at top level
        if "design_changes" in innovation_json:
            key_info["design_changes"] = innovation_json["design_changes"]
        if "workflow_change" in innovation_json:
            key_info["workflow_change"] = innovation_json["workflow_change"]
        
        return key_info

    def _build_user_prompt(
        self,
        retrieved_papers: List[str],
        methods_latex_content: str,
        innovation_json: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Build the user prompt for the LLM.
        
        Args:
            retrieved_papers: List of retrieved paper sections containing methodology and problem statements
                from related papers (methods + limitations + results)
            methods_latex_content: Complete LaTeX Methods section content
            innovation_json: Optional innovation synthesis JSON for structured information
            
        Returns:
            Formatted user prompt string
        """
        if not retrieved_papers:
            raise ValueError("retrieved_papers is required and cannot be empty.")
        if not methods_latex_content or not methods_latex_content.strip():
            raise ValueError("methods_latex_content is required and cannot be empty.")

        papers_payload = self._normalize_retrieved_papers(retrieved_papers)

        payload: Dict[str, Any] = {
            "retrieved_papers": papers_payload,
            "methods_section": methods_latex_content.strip(),
        }
        
        # Add innovation JSON key info if provided
        if innovation_json:
            key_info = self._extract_key_info(innovation_json)
            if key_info:
                payload["innovation_key_info"] = key_info

        payload_text = json.dumps(payload, ensure_ascii=False, indent=2)
        
        reminder = """Remember:
- **PRIORITY: Use structured information from innovation_key_info if provided** - The innovation_key_info contains authoritative structured data about the method name, problem statement, research question, limitations, and innovations. Use this information as the primary source, and supplement with information from retrieved papers and Methods LaTeX section.
- Extract the method name from innovation_key_info.final_proposal_topic (if available) or from the Methods LaTeX section, and use it consistently throughout (replace [OUR METHOD NAME]).
- Use innovation_key_info.final_problem_statement for the problem statement (if available).
- Use innovation_key_info.method_context.research_question and problem_gap for research context (if available).
- Use innovation_key_info.module_weaknesses for limitations of existing approaches - these are more accurate than extracting from LaTeX (if available).
- Use innovation_key_info.module_innovations and selected_pipeline.rationale for describing how our method addresses limitations and highlighting advantages (if available).
- Extract key method innovations, components, and architecture from the Methods LaTeX section.
- Ground all claims about SOTA methods and limitations based on information in innovation_key_info (if provided) or the retrieved papers.
- **DO NOT include any citations** (no \\cite, \\citep, or any citation commands).
- Base experimental performance summary on provided results or reasonable expectations.
- Ensure smooth logical flow: background → limitations → our method → contributions.
- Write in formal academic tone, confident but not exaggerated.
- Replace all bracketed placeholders with concrete, grounded content.
- Output only the LaTeX Introduction section wrapped in ```latex ... ``` blocks.
"""
        
        return f"{payload_text}\n\n{reminder}"

    @staticmethod
    def _extract_latex_block(response: str) -> Optional[str]:
        """
        Extract LaTeX content from response wrapped in ```latex ... ``` blocks.
        
        This mirrors the behavior of MethodsWritingAgent and MainResultsWritingAgent
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
                    "IntroductionWritingAgent: extracted latex block (length=%d chars)",
                    len(content),
                )
                return content
            
            # Fallback: any fenced code block
            code_block_pattern = r"```\w*\s*\n?(.*?)```"
            code_match = re.search(code_block_pattern, response, re.DOTALL)
            if code_match:
                logger.warning(
                    "IntroductionWritingAgent: no ```latex block found, using generic code block"
                )
                return code_match.group(1).strip()
            
            logger.warning(
                "IntroductionWritingAgent: missing ```latex block in response"
            )
            logger.debug("Full response (truncated):\n%s", response[:1000])
            return None
            
        except Exception as exc:
            logger.warning(
                "IntroductionWritingAgent: failed to extract LaTeX block: %s", exc
            )
            logger.debug("Full response (truncated):\n%s", response[:1000])
            return None

    async def generate_introduction_section(
        self,
        retrieved_papers: List[str],
        methods_latex_content: str,
        *,
        innovation_json: Optional[Dict[str, Any]] = None,
        temperature: float = 0.7,
        max_tokens: int = 8000,
        model: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Generate the Introduction section based on retrieved papers, Methods LaTeX, and innovation JSON.
        
        Args:
            retrieved_papers: List of retrieved paper sections, each containing methodology and 
                problem statements from related papers (methods + limitations + results) (required)
                These should be combined from methodology_items: problem_statement + methodology
            methods_latex_content: Complete LaTeX Methods section content (required)
                This should be the content from innovation_synthesis_methods.tex
            innovation_json: Optional innovation synthesis JSON from InnovationSynthesisAgent
                If provided, structured information (method name, problem statement, limitations, 
                innovations) will be extracted and used as the primary source for these fields.
                This ensures consistency and accuracy in the Introduction section.
            temperature: Temperature for generation (default: 0.7)
            max_tokens: Maximum tokens for generation (default: 8000)
            model: Model name (optional, uses service default)
            
        Returns:
            Dictionary containing:
                - content: The generated LaTeX Introduction section
                - raw_response: Full raw response from the model
                - usage: Token usage statistics
                
        Raises:
            ValueError: If required inputs are missing or if generation fails after retries
        """
        
        user_content = self._build_user_prompt(
            retrieved_papers=retrieved_papers,
            methods_latex_content=methods_latex_content,
            innovation_json=innovation_json,
        )

        async def _attempt(attempt_number: int) -> Optional[Dict[str, Any]]:
            messages = [
                {"role": "system", "content": self.SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ]
            
            logger.info(
                "IntroductionWritingAgent attempt %d (payload chars=%d)",
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
                    "IntroductionWritingAgent: empty response from chat_completion"
                )
                return None

            latex_content = self._extract_latex_block(response)
            if latex_content is None or "\\section{Introduction}" not in latex_content:
                logger.warning(
                    "IntroductionWritingAgent: failed to extract valid LaTeX Introduction section"
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
                "IntroductionWritingAgent failed to produce a valid response after retries."
            )

        return result


__all__ = ["IntroductionWritingAgent"]

