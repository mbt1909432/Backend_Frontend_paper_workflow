"""
Preliminary Writing Agent - 专门用于撰写学术论文的 Preliminary 部分
基于 innovation_synthesis.json 和 methods.tex，提取关键基础概念和公式，
生成一个连续的 Preliminary 段落，为后续 Methods 部分建立基础概念
"""
import json
import re
from typing import Any, Dict, Optional

from tenacity import AsyncRetrying, retry_if_result, stop_after_attempt, wait_exponential

from app.services.openai_service import OpenAIService
from app.utils.logger import logger


class PreliminaryWritingAgent:
    """
    Agent responsible for composing the Preliminary section as a single continuous paragraph.
    
    The Preliminary section introduces 2-3 fundamental prerequisite concepts and key formulas
    that are necessary to understand the methods described in the Methods section. It extracts
    core concepts from innovation_synthesis.json and identifies key formulas from methods.tex
    that need to be explained before the detailed method description.
    
    The output is a SINGLE, CONTINUOUS paragraph (no line breaks, no paragraph separators)
    that flows naturally from one concept to another, embedding key formulas using
    \begin{equation} ... \end{equation} environments.
    """

    SYSTEM_PROMPT = """# Role Definition

You are a top-tier AI research writing assistant with NeurIPS/ICLR/ICML/CVPR/ACL-level expertise.

You excel at:
- Identifying fundamental prerequisite concepts that need to be explained before detailed methods
- Extracting key mathematical formulas and their intuitive meanings
- Synthesizing core concepts from structured JSON and LaTeX content
- Writing concise, continuous academic prose that establishes foundational knowledge
- Embedding mathematical formulas naturally into flowing text
- Following LaTeX formatting conventions

---

# Core Task

Given:
- innovation_json: Structured JSON from InnovationSynthesisAgent containing:
  - module_blueprints.modules[]: Each module's original_role, key_mechanism, and improvement information
  - method_context: Research question and problem domain context
  - final_method_proposal_text: High-level method overview
  - Any fundamental assumptions or theoretical foundations
  
- methods_latex_content: Complete LaTeX Methods section that references various concepts and formulas
  - This helps identify which concepts are used but not yet explained
  - Key formulas that appear in Methods but need prior explanation
  - Technical terminology that requires definition

Your job is to:
1. **Extract 2-3 fundamental prerequisite concepts** from the innovation_json:
   - Core theoretical foundations needed to understand the method
   - Fundamental assumptions or principles
   - Basic mathematical formulations that serve as building blocks
   - Key domain-specific concepts that readers must understand first

2. **Identify key formulas from methods_latex_content** that:
   - Are foundational and appear early in the Methods section
   - Represent core mathematical relationships
   - Need explanation before detailed method description
   - Are referenced but not fully defined in Methods

3. **Compose a single continuous paragraph** that:
   - Starts with: "Before detailing our method, we first revisit several core concepts: "
   - Introduces 2-3 most fundamental concepts sequentially
   - For each concept: provides concise definition, intuitive explanation, and key formula (if applicable)
   - Uses smooth transitions between concepts (e.g., "Moreover", "Furthermore", "In addition")
   - Embeds formulas using `\begin{equation} ... \end{equation}` environments
   - Flows naturally as one cohesive narrative without paragraph breaks

---

# Output Structure

**CRITICAL: The Preliminary section MUST be written as a SINGLE, CONTINUOUS paragraph with NO paragraph breaks, NO empty lines, and NO bullet points. This is a concise, foundational introduction that flows as one continuous narrative.**

You MUST output a single LaTeX block that exactly follows the structure below, **wrapped inside a single ```latex ... ``` fenced code block**, with no extra commentary before or after.

```latex
\\subsection{Preliminary}

Before detailing our method, we first revisit several core concepts: [CONCEPT 1 - definition and intuitive explanation]. [If applicable: Key formula for concept 1 using \\begin{equation} ... \\end{equation}]. Moreover, [CONCEPT 2 - definition and intuitive explanation]. [If applicable: Key formula for concept 2 using \\begin{equation} ... \\end{equation}]. Furthermore, [CONCEPT 3 - definition and intuitive explanation if a third concept is essential]. [If applicable: Key formula for concept 3 using \\begin{equation} ... \\end{equation}]. These foundational concepts form the basis for understanding our proposed method.
```

---

# Critical Constraints

- **SINGLE paragraph format**: The entire Preliminary section MUST be written as a SINGLE paragraph with NO paragraph breaks, NO empty lines between sentences, and NO bullet points. **DO NOT use bullet points, itemize environments (`\\begin{itemize} ... \\end{itemize}`), enumerate environments (`\\begin{enumerate} ... \\end{enumerate}`), paragraph separators (`\\paragraph{}`), or any line breaks that create multiple paragraphs**. This is a concise, foundational introduction that flows as one continuous narrative.

- **2-3 core concepts only**: Focus on the 2-3 MOST fundamental prerequisite concepts that readers absolutely must understand before reading the Methods section. Do not include every concept—only the essential foundations.

- **Extract from provided sources**: 
  - Extract fundamental concepts from `module_blueprints.modules[].original_role` and `module_blueprints.modules[].key_mechanism`
  - Identify key formulas from `methods_latex_content` that need prior explanation
  - Use `method_context` to understand the domain and determine which concepts are foundational
  - Reference `final_method_proposal_text` to understand what background is needed

- **Opening phrase**: MUST start with exactly: "Before detailing our method, we first revisit several core concepts: "

- **Smooth transitions**: Use appropriate transition words/phrases to connect concepts:
  - Between first and second concept: "Moreover", "Furthermore", "In addition", "Additionally"
  - Between second and third concept: "Furthermore", "Additionally", "Finally" (if third is the last)

- **Mathematical Equations Format**: 
  - All displayed mathematical equations MUST use `\\begin{equation} ... \\end{equation}` environment
  - NEVER use `$$ ... $$`, `\\[ ... \\]`, or `\\( ... \\)` for displayed equations
  - Inline math can use `$ ... $` or `\\( ... \\)`
  - Each displayed equation should have proper labels (e.g., `\\label{eq:concept_name}`) for cross-referencing
  - Provide clear symbol definitions within the paragraph text before or after each equation

- **Complete symbol definitions**: Every mathematical symbol used in formulas MUST be clearly defined in the paragraph text. For each symbol in an equation, provide:
  - What the symbol represents
  - Its meaning in the context
  - Its dimensions or domain where applicable

- **Concise but complete**: Keep the paragraph concise (typically 150-250 words), but ensure each concept is:
  - Clearly defined
  - Intuitively explained
  - Mathematically formalized (if applicable)
  - Connected to the method being proposed

- **Formal academic tone**: Maintain confident, precise, non-exaggerated writing style. Use formal academic language.

- **No placeholders**: Replace all bracketed placeholders with concrete, grounded content extracted from the provided sources.

- **LaTeX formatting**: Use proper LaTeX syntax and formatting conventions. Ensure proper escaping of special characters.

---

# Tone & Style

- Formal academic tone: confident, precise, non-exaggerated
- Concise: focus on essential concepts only
- Pedagogical: explain concepts clearly for readers who may not be experts
- Smooth flow: use natural transitions to connect concepts
- Mathematical rigor: include formal definitions where appropriate, but maintain intuitive explanations

---

# Output Format

- Output the complete LaTeX Preliminary subsection wrapped in a single ```latex ... ``` fenced code block
- Do not include any other text outside the code block
- Ensure the output is a single continuous paragraph with no breaks
"""

    def __init__(self, openai_service: OpenAIService):
        """
        Initialize the Preliminary Writing Agent.
        
        Args:
            openai_service: OpenAI service instance for API calls
        """
        self.openai_service = openai_service

    @staticmethod
    def _extract_key_info(innovation_json: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract key information needed for Preliminary section generation.
        
        Args:
            innovation_json: Full JSON from InnovationSynthesisAgent
            
        Returns:
            Simplified JSON containing only essential fields for Preliminary section
        """
        key_info = {}
        
        # 1. Research context (to understand the domain)
        if "method_context" in innovation_json:
            method_context = innovation_json["method_context"]
            key_info["method_context"] = {
                "research_question": method_context.get("research_question", ""),
                "problem_gap": method_context.get("problem_gap", ""),
                "target_scenario": method_context.get("target_scenario", ""),
            }
        
        # 2. High-level method overview (to understand what background is needed)
        if "final_method_proposal_text" in innovation_json:
            key_info["final_method_proposal_text"] = innovation_json["final_method_proposal_text"]
        
        # 3. Module blueprints (to extract fundamental concepts)
        if "module_blueprints" in innovation_json:
            module_blueprints = innovation_json["module_blueprints"]
            if "modules" in module_blueprints:
                key_info["core_concepts"] = []
                for module in module_blueprints["modules"]:
                    module_info = {
                        "module_id": module.get("id", ""),
                        "original_role": module.get("original_role", ""),
                        "key_mechanism": module.get("key_mechanism", ""),
                    }
                    # Extract improvement info if it contains foundational concepts
                    improvement = module.get("improvement", {})
                    if improvement:
                        if "design_changes" in improvement:
                            module_info["design_changes"] = improvement["design_changes"]
                        if "math_spec" in improvement:
                            # Include basic math spec if it represents a foundational concept
                            math_spec = improvement.get("math_spec", "")
                            if math_spec and len(math_spec) < 500:  # Only include concise foundational formulas
                                module_info["math_spec"] = math_spec
                    key_info["core_concepts"].append(module_info)
        
        # 4. Theoretical foundations (if available)
        if "theoretical_and_complexity" in innovation_json:
            theoretical = innovation_json["theoretical_and_complexity"]
            if "assumptions" in theoretical:
                key_info["assumptions"] = theoretical["assumptions"]
        
        return key_info

    @staticmethod
    def _extract_latex_block(response: str) -> Optional[str]:
        """
        Extract LaTeX content from response, handling ```latex code blocks.
        
        Args:
            response: Raw response from the model
            
        Returns:
            Extracted LaTeX content, or None if not found
        """
        try:
            # First try to find ```latex block
            latex_pattern = r'```latex\s*\n?(.*?)```'
            latex_match = re.search(latex_pattern, response, re.DOTALL)
            if latex_match:
                latex_content = latex_match.group(1).strip()
                # Remove leading/trailing whitespace but preserve structure
                return latex_content
            else:
                # Try to find any code block as fallback
                code_block_pattern = r'```\w*\s*\n?(.*?)```'
                code_match = re.search(code_block_pattern, response, re.DOTALL)
                if code_match:
                    logger.warning("No ```latex block found, using generic code block")
                    return code_match.group(1).strip()
                
                logger.warning("PreliminaryWritingAgent: missing ```latex block in response")
                logger.debug("Full response:\n%s", response[:1000])
                return None
                
        except Exception as exc:
            logger.warning("PreliminaryWritingAgent: failed to extract LaTeX block: %s", exc)
            logger.debug("Full response:\n%s", response[:1000])
            return None

    async def generate_preliminary_section(
        self,
        innovation_json: Dict[str, Any],
        methods_latex_content: str,
        temperature: float = 0.7,
        max_tokens: int = 2000,
        model: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Generate the Preliminary section based on innovation_json and methods_latex_content.
        
        Args:
            innovation_json: The JSON object from InnovationSynthesisAgent.generate_innovation_plan()
                This should be the 'output' field from the innovation result.
            methods_latex_content: Complete LaTeX Methods section content
                Used to identify key formulas and concepts that need prior explanation
            temperature: Temperature for generation (default: 0.7)
            max_tokens: Maximum tokens for generation (default: 2000, sufficient for concise paragraph)
            model: Model name (optional, uses service default)
            
        Returns:
            Dictionary containing:
            - content: The generated LaTeX Preliminary section
            - raw_response: Full raw response from the model
            - usage: Token usage statistics
        """
        
        # Extract key information needed for Preliminary section
        key_info = self._extract_key_info(innovation_json)
        
        # Convert the key info to a formatted string for the prompt
        try:
            json_str = json.dumps(key_info, indent=2, ensure_ascii=False)
            logger.debug(
                "PreliminaryWritingAgent: extracted key info (original size: %d keys, key info size: %d keys)",
                len(innovation_json),
                len(key_info)
            )
        except (TypeError, ValueError) as exc:
            logger.error("PreliminaryWritingAgent: failed to serialize key_info: %s", exc)
            raise ValueError(f"Invalid innovation_json format: {exc}") from exc
        
        # Truncate methods_latex_content if too long (keep first 8000 chars which usually contains key formulas)
        methods_preview = methods_latex_content[:8000] if len(methods_latex_content) > 8000 else methods_latex_content
        if len(methods_latex_content) > 8000:
            logger.info("PreliminaryWritingAgent: truncated methods_latex_content from %d to 8000 chars", len(methods_latex_content))
        
        user_content = f"""Please compose the Preliminary section based on the following information:

**1. Core Concepts from Innovation Synthesis JSON:**
{json_str}

**2. Methods LaTeX Content (first 8000 chars, to identify key formulas that need prior explanation):**
{methods_preview}

**Instructions:**
- Extract 2-3 MOST fundamental prerequisite concepts that readers must understand before reading the Methods section
- Identify key formulas from the Methods section that need to be introduced early (these are formulas that appear in Methods but represent foundational concepts)
- Compose a SINGLE, CONTINUOUS paragraph (no paragraph breaks, no empty lines) that:
  * Starts with: "Before detailing our method, we first revisit several core concepts: "
  * Introduces each concept sequentially with smooth transitions
  * Provides concise definitions and intuitive explanations
  * Embeds key formulas using `\\begin{{equation}} ... \\end{{equation}}` environments with proper labels
  * Defines all mathematical symbols clearly in the paragraph text
  * Flows naturally from one concept to the next
- Keep it concise (150-250 words) but complete
- Use formal academic tone
- Output only the LaTeX content wrapped in ```latex ... ``` blocks."""

        async def _attempt(attempt_number: int) -> Optional[Dict[str, Any]]:
            messages = [
                {"role": "system", "content": self.SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ]

            logger.info(
                "PreliminaryWritingAgent attempt %d (innovation_json keys: %d, methods_latex length: %d chars)",
                attempt_number,
                len(innovation_json),
                len(methods_latex_content),
            )

            # Adjust temperature for retries (more deterministic)
            adjusted_temperature = max(0.3, temperature - (attempt_number - 1) * 0.1)

            response, usage = await self.openai_service.chat_completion(
                messages=messages,
                temperature=adjusted_temperature,
                max_tokens=max_tokens,
                model=model,
            )

            latex_content = self._extract_latex_block(response)
            if latex_content is None:
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
                "PreliminaryWritingAgent failed to produce valid LaTeX output after retries."
            )

        return result

