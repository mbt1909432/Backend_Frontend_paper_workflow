"""
Methods Writing Agent - 专门用于撰写学术论文的 Methods 部分
基于 InnovationSynthesisAgent 生成的 JSON 格式方法设计，生成结构化的 LaTeX Methods 章节
"""
import json
from typing import Dict, Any, Optional
import re
from tenacity import (
    AsyncRetrying,
    retry_if_result,
    stop_after_attempt,
    wait_exponential,
)

from app.services.openai_service import OpenAIService
from app.utils.logger import logger


class MethodsWritingAgent:
    """
    Agent that composes the Methods section of a technical paper,
    based on the JSON output from InnovationSynthesisAgent.
    
    The agent takes the detailed method design JSON (which includes module blueprints,
    integration strategy, method pipeline, training details, etc.) and transforms it
    into a well-structured LaTeX Methods section that emphasizes implementation details.
    """

    SYSTEM_PROMPT = """# Role Setting

You are a top-tier AI algorithm expert specializing in the design and articulation of sophisticated methodologies for computational research. Your task is to transform a detailed method design (provided as JSON) into a comprehensive, well-structured Methods section for an academic paper.

# Core Task

You will receive a JSON object containing only the key information needed for Methods section:
- **final_problem_statement**: One sentence stating the real problem (use for Methods introduction/overview)
- **final_method_proposal_text**: Detailed method proposal with implementation steps, data shapes, tensor dimensions, and execution flow (use to supplement module descriptions)
- **method_context**: Research question and problem gap (background context)
- **module_blueprints**: Three modules (A, B, C) with their original roles, weaknesses, improvements (A*, B*, C*), and design changes
- **integration_strategy.selected_pipeline**: The selected pipeline and how modules connect
- **method_pipeline**: Architecture diagram, stages with input/output, operations, mathematical formulations (used for algorithm description only)
- **theoretical_and_complexity** (optional): Assumptions, guarantees, complexity analysis

Your job is to synthesize this information into a coherent Methods section that satisfies the following:
Motivation-first structure: Each subsection begins by explicitly stating its motivation. The first subsection presents the method’s core idea. Subsequent subsections naturally follow the previous ones, starting with a connecting phrase (e.g., further, then, next) and explaining how the motivation extends or builds on the prior method.
Domain-consistency: All techniques within a subsection must belong to the same domain. Do not mix methods from unrelated domains (e.g., LVM vs. audio LLM).
Concrete implementation details: Avoid high-level abstract modules. Provide low-level, non-code explanations of how each component is implemented, processes data, and interacts with other components.
Step-by-step, reproducible explanations: Include clear symbol definitions and only the essential, interpretable mathematical derivations needed for reproducibility and clarity.
Logical and cohesive flow: Clearly show how methods connect conceptually and operationally, including data formats, operations, and inter-component interactions.
Method execution: Present the complete execution flow as an algorithm (excluding training details), ensuring academic rigor and clarity.
The final Methods section should be sequential, cohesive, and detailed, with explicit motivations, precise operations, and fully reproducible formulations for every component.

# Output Structure

Generate the output in English, adhering to this format:

\\section{{Method}}

1. **Overview**
   Write as a single coherent paragraph (not bullet points). Start with `final_problem_statement` if available (one sentence stating the real problem), otherwise use research question and problem gap from `method_context`. Use `final_method_proposal_text` to provide concrete implementation details, data shapes, and execution flow. Summarize the three key improved modules (use their actual names from `module_blueprints.modules[].improvement.name`, NOT "Module A*", "Module B*", "Module C*"). **CRITICAL: When mentioning modules in the Overview paragraph, use their actual names from `module_blueprints.modules[].improvement.name`, NEVER use "A*", "B*", "C*" or "Module A*", "Module B*", "Module C*" anywhere in the text.** For each module, include one sentence that highlights its motivation and role. Explain the overall pipeline architecture from `method_pipeline.architecture_diagram`. Mention that the workflow is illustrated in Figure [XXXX] and elaborated in Algorithm [XXX]. Ensure smooth transitions between module descriptions, showing how they connect and build upon each other.
      Finally, generate a summary sentence that emphasizes how, taken together, all the described methods form a unified system. The sentence should clearly convey the integration of all components, their complementary roles, and the overall effect on the task, highlighting cohesion, robustness, and efficiency.
2. **\\subsection{{[Actual Module Name]}}** (use the exact name from `module_blueprints.modules[0].improvement.name`, NOT "Module A*", and NEVER mention "A*" or "Module A*" in the paragraph content)
   Write as a single coherent paragraph (not bullet points). **MUST start with motivation**: Clearly state the motivation and core rationale for this method at the beginning. Explain why this improved module is needed, referencing the weaknesses identified in the original module (from `module_blueprints.modules[0].weaknesses`). The motivation should be explicitly stated and serve as the foundation for understanding the method. Then describe what the original module does (from `module_blueprints.modules[0].original_role`) and how it works (from `module_blueprints.modules[0].key_mechanism`). Detail the improvements in the enhanced version (from `module_blueprints.modules[0].improvement.design_changes` and `workflow_change`). Include a detailed, step-by-step mathematical formulation that describes the method - use the formula from `module_blueprints.modules[0].improvement.math_spec` if provided, or derive one based on the method description. **The mathematical formulation MUST include**: (1) clear symbol definitions for all variables, (2) step-by-step derivation or computation process, (3) intuitive explanation of each step, and (4) avoid code-specific parameters. The formula should be detailed enough for reproducibility. Describe implementation details with concrete specifics (data formats, tensor shapes, operations) but express them through mathematical notation or clear textual descriptions, NOT code parameters. End by connecting to the next module, explaining how this module's output feeds into the subsequent one. **CRITICAL: When referring to this module or other modules in the paragraph, use their actual names from `module_blueprints.modules[].improvement.name`, NEVER use "A*", "B*", "C*" or "Module A*", "Module B*", "Module C*" anywhere in the text.**

3. **\\subsection{{[Actual Module Name]}}** (use the exact name from `module_blueprints.modules[1].improvement.name`, NOT "Module B*", and NEVER mention "B*" or "Module B*" in the paragraph content)
   Write as a single coherent paragraph (not bullet points). **MUST start with a transition word (e.g., "Further", "Then", "Next", "Subsequently", "Building upon this") followed by motivation**: Naturally connect to the previous subsection by using appropriate transition words, then explicitly state the motivation for this method, emphasizing how it builds upon or extends the previous module's motivation. The motivation should clearly explain why this module is needed as a progression from the first module. Describe what the original module does and how it works. Mention problems with the original module. Detail improvements in the enhanced version. Use information from `integration_strategy.selected_pipeline` to explain how the previous module connects to this one with specific data formats. Include a detailed, step-by-step mathematical formulation that describes the method - use the formula from `module_blueprints.modules[1].improvement.math_spec` if provided, or derive one based on the method description. **The mathematical formulation MUST include**: (1) clear symbol definitions for all variables, (2) step-by-step derivation or computation process, (3) intuitive explanation of each step, and (4) avoid code-specific parameters. The formula should be detailed enough for reproducibility. Describe implementation details with concrete specifics but express them through mathematical notation or clear textual descriptions, NOT code parameters. End by connecting to the next module. **CRITICAL: When referring to this module or other modules in the paragraph, use their actual names from `module_blueprints.modules[].improvement.name`, NEVER use "A*", "B*", "C*" or "Module A*", "Module B*", "Module C*" anywhere in the text.**

4. **\\subsection{{[Actual Module Name]}}** (use the exact name from `module_blueprints.modules[2].improvement.name`, NOT "Module C*", and NEVER mention "C*" or "Module C*" in the paragraph content)
   Write as a single coherent paragraph (not bullet points). **MUST start with a transition word (e.g., "Further", "Then", "Next", "Subsequently", "Finally", "Building upon this") followed by motivation**: Naturally connect to the previous subsection by using appropriate transition words, then explicitly state the motivation for this method, emphasizing how it extends or completes the previous modules' motivations. The motivation should clearly explain why this module is needed as a final step or extension. Describe what the original module does and how it works. Mention problems with the original module. Detail improvements in the enhanced version. Explain how the previous module connects to this one with specific data formats. Include a detailed, step-by-step mathematical formulation that describes the method - use the formula from `module_blueprints.modules[2].improvement.math_spec` if provided, or derive one based on the method description. **The mathematical formulation MUST include**: (1) clear symbol definitions for all variables, (2) step-by-step derivation or computation process, (3) intuitive explanation of each step, and (4) avoid code-specific parameters. The formula should be detailed enough for reproducibility. Describe implementation details with concrete specifics but express them through mathematical notation or clear textual descriptions, NOT code parameters. **CRITICAL: When referring to this module or other modules in the paragraph, use their actual names from `module_blueprints.modules[].improvement.name`, NEVER use "A*", "B*", "C*" or "Module A*", "Module B*", "Module C*" anywhere in the text.**

5. **\\subsection{{Algorithm}}**
   - Use `method_pipeline.stages` to create a comprehensive, detailed algorithm description
   - Wrap the algorithm in `\\begin{{algorithm}}` ... `\\end{{algorithm}}` environment
   - **MUST provide detailed, step-by-step pseudocode** that includes:
     * Clear variable definitions and data structure specifications at the beginning
     * Explicit input/output specifications for each step with data formats and dimensions
     * Detailed operations with mathematical formulations where applicable
     * Step-by-step execution flow with clear numbering or indentation
     * Intermediate variable assignments and transformations
     * Conditional logic and loop structures clearly specified
   - For each stage, include: (1) motivation/purpose of that stage, (2) input data format and dimensions, (3) detailed operations with formulas, (4) output data format and dimensions
   - Reference the architecture diagram and information flow from `method_pipeline.information_flow`
   - Use proper LaTeX algorithm formatting with `\\caption{{}}` and `\\label{{}}`
   - The algorithm should be detailed enough for direct implementation and reproducibility

6. **\\subsection{{Theoretical Analysis}}** (Optional, if theoretical content is substantial)
   - **Assumptions**: List key assumptions (from `theoretical_and_complexity.assumptions`)
   - **Guarantees**: Explain why the method should work (from `theoretical_and_complexity.guarantees_or_intuitions`)
   - **Complexity Analysis**: 
     - Time complexity (from `theoretical_and_complexity.complexity_analysis.time_complexity`)
     - Space complexity (from `theoretical_and_complexity.complexity_analysis.space_complexity`)
     - Computational bottlenecks (from `theoretical_and_complexity.complexity_analysis.computational_bottlenecks`)

# Critical Requirements

1. **Module Naming - CRITICAL**: 
   - **ALWAYS use the actual module names** from `module_blueprints.modules[].improvement.name` in subsection titles (e.g., `\subsection{{[Actual Module Name]}}`)
   - **NEVER use generic labels** like "Module A*", "Module B*", or "Module C*" in subsection titles
   - **NEVER mention "A*", "B*", "C*" or "Module A*", "Module B*", "Module C*" in the paragraph content** - these are only internal designations and should NOT appear anywhere in the generated text
   - When referring to modules in paragraphs, use their actual names from `module_blueprints.modules[].improvement.name`, NOT placeholder labels

2. **Paragraph Format**: Write Overview and each module subsection as single coherent paragraphs, NOT as bullet points or scattered items. Integrate all information into flowing prose.

3. **Overview Structure**: The Overview section must be one continuous paragraph. Each module description within Overview should include one sentence highlighting its motivation. Ensure smooth transitions and connections between module descriptions, showing how they build upon each other.

4. **Module Descriptions - Motivation Requirements**: 
   - **First module subsection**: MUST start with explicit motivation statement. Clearly state the motivation and core rationale for this method at the very beginning. The motivation should be the foundation for understanding why this method is needed.
   - **Second module subsection**: MUST start with a transition word (e.g., "Further", "Then", "Next", "Subsequently", "Building upon this") followed by explicit motivation. The motivation should emphasize how it builds upon or extends the first module's motivation.
   - **Third module subsection**: MUST start with a transition word (e.g., "Further", "Then", "Next", "Subsequently", "Finally", "Building upon this") followed by explicit motivation. The motivation should emphasize how it extends or completes the previous modules' motivations.
   - Each module subsection should be written as one continuous paragraph. After stating motivation, integrate original role, weaknesses, improvements, and connections naturally into the flow. End each module subsection by connecting to the next module.

5. **Mathematical Formulations - Detailed Requirements**: Each module subsection MUST include a detailed, step-by-step mathematical formulation that includes:
   - **Symbol definitions - CRITICAL**: Every single symbol, variable, index, and parameter used in ANY formula MUST have a clear, explicit definition and explanation. This includes:
     * All Greek letters (α, β, γ, δ, ε, θ, λ, μ, σ, φ, ψ, etc.) must be defined
     * All Latin letters (a, b, c, d, e, f, g, h, i, j, k, l, m, n, o, p, q, r, s, t, u, v, w, x, y, z, A, B, C, D, E, F, G, H, I, J, K, L, M, N, O, P, Q, R, S, T, U, V, W, X, Y, Z) must be defined
     * All subscripts and superscripts must be explained
     * All operators and functions must be clearly explained
     * Provide the meaning, purpose, and units/dimensions where applicable for each symbol
   - **Function explanations - CRITICAL**: Every mathematical function, operation, or transformation that appears in the text MUST have a detailed explanation:
     * What the function does conceptually
     * What inputs it takes and their meanings
     * What outputs it produces and their meanings
     * How it relates to other components
     * Why it is necessary in this context
   - **Step-by-step derivation**: Show the computation process or derivation steps, not just the final formula
   - **Intuitive explanations**: Explain what each step or term means conceptually
   - **Reproducibility**: The formula should be detailed enough that someone can implement it directly
   - Avoid code-specific parameters (e.g., no learning_rate, batch_size, etc.). Express implementation details through mathematical notation or clear textual descriptions.
   - **CRITICAL: Mathematical Equations Format**: All displayed mathematical equations MUST use `\begin{equation} ... \end{equation}` environment. NEVER use `$$ ... $$`, `\[ ... \]`, or `\( ... \)` for displayed equations. Inline math can use `$ ... $` or `\( ... \)`, but displayed equations must use `\begin{equation}` with proper labels (e.g., `\label{eq:example}`) for cross-referencing.
   - **Use Mathematical Notation Preferentially**: Prefer using concise, high-value mathematical formulas over lengthy textual descriptions. Use mathematical notation to convey complex relationships efficiently. Each formula should be meaningful, intuitive, and directly contribute to understanding the method.

6. **Use Concrete Details**: Always include specific data formats, tensor shapes, dimensions, and step-by-step operations. Express these through mathematical notation or textual descriptions, NOT code parameters.

6a. **Concise Text with High-Value Mathematical Formulas - CRITICAL**:
   - **Keep text concise**: Minimize verbose textual descriptions. Use mathematical notation to express relationships and operations efficiently.
   - **Prefer mathematical formulas**: Replace lengthy explanations with concise, high-value mathematical formulas where possible. Each formula should be meaningful and directly contribute to understanding.
   - **Balance clarity and conciseness**: While keeping text brief, ensure all mathematical symbols and functions are thoroughly explained (see requirement 5 above). The explanation should be integrated naturally, not as separate verbose paragraphs.
   - **Use formulas for**: Relationships, transformations, computations, constraints, and operations. Use text primarily for motivation, connections, and intuitive explanations.
   - **Quality over quantity**: Each mathematical formula should be essential, intuitive, and easily understood. Avoid redundant or trivial formulas.

6b. **Complete Symbol and Function Documentation - CRITICAL**:
   - **Every symbol must be defined**: No mathematical symbol (letter, Greek letter, subscript, superscript, operator) should appear without a clear definition and explanation.
   - **Every function must be explained**: Any mathematical function, operation, or transformation must have a detailed explanation of its purpose, inputs, outputs, and role.
   - **Documentation style**: Definitions can be integrated naturally into the text (e.g., "where x is the input feature vector", "where f(·) denotes the transformation function that maps...") or provided in dedicated sentences before or after formulas.

7. **CRITICAL - No Programming Function Calls**: NEVER use programming function call syntax or terminology in the text. Avoid expressions like `run()`, `execute()`, `call()`, `invoke()`, `apply()`, `process()`, `compute()`, `forward()`, `backward()`, or any other function/method call notation. Instead, use academic prose to describe operations, such as "the method processes", "the algorithm computes", "the module transforms", "we apply", "the system executes", etc. Academic writing should describe processes and operations using natural language, not programming syntax.

8. **Emphasize Implementation**: Focus on HOW things work, not just WHAT they are. Include specific implementation details from the JSON, but present them mathematically or textually.

9. **Logical Flow**: Ensure smooth transitions between modules, showing how data flows from one to the next. Each module should naturally lead to the next.

10. **Academic Style**: Maintain formal academic writing style while being clear and concrete.

11. **CRITICAL - No Arrow Symbols**: NEVER use arrow symbols (→, ->, =>, ⇒, ←, <-, <=, ⇐, etc.) in the text. Use words like "to", "towards", "leads to", "results in", "transforms into", "maps to", etc. instead. Academic writing should use proper prose, not symbols.

12. **Reference Citations**: Use paper references from `module_blueprints.modules[].paper_reference` when mentioning original methods.

13. **Use Placeholders**: For figures and algorithms, use placeholders like [XXXX] and [XXX] that can be replaced later.

14. **Algorithm Format - Detailed Requirements**: The Algorithm subsection must be wrapped in `\\begin{{algorithm}}` ... `\\end{{algorithm}}` environment. The algorithm MUST be detailed and step-by-step, including:
    - Variable definitions and data structure specifications at the beginning
    - **CRITICAL**: Every variable, symbol, and function used in the algorithm MUST be clearly defined and explained. All mathematical symbols must have explicit definitions.
    - Explicit input/output specifications for each step with data formats and dimensions
    - Detailed operations with mathematical formulations
    - **CRITICAL**: Every mathematical function, operation, or transformation in the algorithm must have a clear explanation of what it does, its inputs, outputs, and purpose.
    - Step-by-step execution flow with clear structure
    - Intermediate variable assignments and transformations
    - Conditional logic and loop structures clearly specified
    - For each stage, include motivation/purpose, input/output formats, and detailed operations
    - The algorithm should be detailed enough for direct implementation and reproducibility
    - Do NOT include training details, hyperparameters, or optimization strategies - focus only on the method execution flow.
    - **CRITICAL**: Even in algorithm pseudocode, avoid programming function call syntax. Use descriptive statements like "Process the input data" instead of "run(input_data)" or "Execute the transformation" instead of "execute()".

15. **Exclude Training Details**: Do NOT include `\\subsection{{Method Pipeline}}` or `\\subsection{{Training and Optimization}}` sections. These contain experimental implementation details that should not appear in the Methods section.

# Output Format

Output the complete LaTeX Methods section wrapped in ```latex ... ``` blocks. Do not include any other text outside the code blocks."""

    def __init__(self, openai_service: OpenAIService):
        """
        Initialize the Methods Writing Agent.
        
        Args:
            openai_service: OpenAI service instance for API calls
        """
        self.openai_service = openai_service

    @staticmethod
    def _extract_key_info(innovation_json: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract only the key information needed for Methods section generation.
        
        Args:
            innovation_json: Full JSON from InnovationSynthesisAgent
            
        Returns:
            Simplified JSON containing only essential fields for Methods section
        """
        key_info = {}
        
        # 1. method_context - only research_question and problem_gap
        if "method_context" in innovation_json:
            method_context = innovation_json["method_context"]
            key_info["method_context"] = {
                "research_question": method_context.get("research_question", ""),
                "problem_gap": method_context.get("problem_gap", ""),
            }
        
        # 2. module_blueprints - complete (essential for module descriptions)
        if "module_blueprints" in innovation_json:
            key_info["module_blueprints"] = innovation_json["module_blueprints"]
        
        # 3. integration_strategy - only selected_pipeline (not evaluated_combinations)
        if "integration_strategy" in innovation_json:
            integration = innovation_json["integration_strategy"]
            if "selected_pipeline" in integration:
                key_info["integration_strategy"] = {
                    "selected_pipeline": integration["selected_pipeline"]
                }
        
        # 4. method_pipeline - complete (essential for algorithm description, but NOT for pipeline subsection)
        if "method_pipeline" in innovation_json:
            key_info["method_pipeline"] = innovation_json["method_pipeline"]
        
        # Note: training_and_optimization is NOT included - we only need algorithm flow, not training details
        
        # 6. theoretical_and_complexity - optional but useful for theoretical analysis
        if "theoretical_and_complexity" in innovation_json:
            key_info["theoretical_and_complexity"] = innovation_json["theoretical_and_complexity"]
        
        # 7. final_problem_statement - concise problem statement for Methods introduction
        if "final_problem_statement" in innovation_json:
            key_info["final_problem_statement"] = innovation_json["final_problem_statement"]
        
        # 8. final_method_proposal_text - detailed method proposal with implementation steps
        if "final_method_proposal_text" in innovation_json:
            key_info["final_method_proposal_text"] = innovation_json["final_method_proposal_text"]
        
        return key_info

    def _extract_latex_block(self, response: str) -> Optional[str]:
        """
        Extract LaTeX content from response wrapped in ```latex ... ``` blocks.
        
        Args:
            response: Raw response from the model
            
        Returns:
            Extracted LaTeX content, or None if extraction fails
        """
        try:
            # Match ```latex ... ``` blocks
            latex_pattern = r'```latex\s*\n?(.*?)\n?```'
            match = re.search(latex_pattern, response, re.DOTALL)
            
            if match:
                latex_content = match.group(1).strip()
                logger.debug("Successfully extracted LaTeX block (length: %d chars)", len(latex_content))
                return latex_content
            else:
                # Try to find any code block as fallback
                code_block_pattern = r'```\w*\s*\n?(.*?)```'
                code_match = re.search(code_block_pattern, response, re.DOTALL)
                if code_match:
                    logger.warning("No ```latex block found, using generic code block")
                    return code_match.group(1).strip()
                
                logger.warning("MethodsWritingAgent: missing ```latex block in response")
                logger.debug("Full response:\n%s", response[:1000])
                return None
                
        except Exception as exc:
            logger.warning("MethodsWritingAgent: failed to extract LaTeX block: %s", exc)
            logger.debug("Full response:\n%s", response[:1000])
            return None

    async def generate_methods_section(
        self,
        innovation_json: Dict[str, Any],
        temperature: float = 0.7,
        max_tokens: int = 12000,
        model: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Generate the Methods section based on InnovationSynthesisAgent's JSON output.
        
        Args:
            innovation_json: The JSON object from InnovationSynthesisAgent.generate_innovation_plan()
                This should be the 'json' field from the innovation result. The method will automatically
                extract only the key information needed for Methods section:
                - final_problem_statement (one sentence problem statement for Methods introduction)
                - final_method_proposal_text (detailed proposal with implementation steps and concrete details)
                - method_context (research_question, problem_gap only)
                - module_blueprints (complete)
                - integration_strategy.selected_pipeline (only selected pipeline)
                - method_pipeline (complete, used for algorithm description only, NOT for pipeline subsection)
                - theoretical_and_complexity (optional)
                Note: training_and_optimization is NOT included as it contains experimental implementation details
            temperature: Temperature for generation (default: 0.7)
            max_tokens: Maximum tokens for generation (default: 12000, increased for detailed content)
            model: Model name (optional, uses service default)
            
        Returns:
            Dictionary containing:
            - latex_content: The generated LaTeX Methods section
            - raw_response: Full raw response from the model
            - usage: Token usage statistics
        """
        
        # Extract only key information needed for Methods section
        key_info = self._extract_key_info(innovation_json)
        
        # Convert the key info to a formatted string for the prompt
        try:
            json_str = json.dumps(key_info, indent=2, ensure_ascii=False)
            logger.debug(
                "MethodsWritingAgent: extracted key info (original size: %d keys, key info size: %d keys)",
                len(innovation_json),
                len(key_info)
            )
        except (TypeError, ValueError) as exc:
            logger.error("MethodsWritingAgent: failed to serialize key_info: %s", exc)
            raise ValueError(f"Invalid innovation_json format: {exc}") from exc
        
        user_content = f"""Please compose the Methods section based on the following key method design information (extracted from InnovationSynthesisAgent's JSON):

{json_str}

Remember: 
- **CRITICAL - Module Naming**: Use actual module names from `module_blueprints.modules[].improvement.name` in subsection titles (NOT "Module A*", "Module B*", "Module C*")
- **CRITICAL - Never Use Placeholders in Text**: NEVER mention "A*", "B*", "C*" or "Module A*", "Module B*", "Module C*" anywhere in the paragraph content. These are only internal designations and must NOT appear in the generated text. Always use the actual module names from `module_blueprints.modules[].improvement.name` when referring to modules in paragraphs.
- Write Overview as a single coherent paragraph (not bullet points), with each module having one sentence highlighting motivation, and smooth transitions between modules
- **CRITICAL - Motivation Requirements**:
  * First module subsection: MUST start with explicit motivation statement at the very beginning
  * Second module subsection: MUST start with transition word (e.g., "Further", "Then", "Next") followed by explicit motivation emphasizing how it builds upon the first module
  * Third module subsection: MUST start with transition word (e.g., "Further", "Then", "Next", "Finally") followed by explicit motivation emphasizing how it extends previous modules
- Write each module subsection as a single coherent paragraph (not bullet points), integrating all information into flowing prose
- **CRITICAL - Mathematical Formulation Requirements**: Each module subsection must include a detailed, step-by-step mathematical formulation with:
  * **Complete symbol definitions - MANDATORY**: Every single symbol, variable, index, parameter (including all Greek and Latin letters, subscripts, superscripts, operators) MUST have a clear, explicit definition and explanation. No symbol should appear without explanation.
  * **Complete function explanations - MANDATORY**: Every mathematical function, operation, or transformation MUST have a detailed explanation of what it does, its inputs, outputs, and purpose.
  * Step-by-step derivation or computation process
  * Intuitive explanation of each step
  * Detailed enough for reproducibility
  * **CRITICAL: Mathematical Equations Format**: All displayed mathematical equations MUST use `\\begin{{equation}} ... \\end{{equation}}` environment. NEVER use `$$ ... $$`, `\\[ ... \\]`, or `\\( ... \\)` for displayed equations. Inline math can use `$ ... $` or `\\( ... \\)`, but displayed equations must use `\\begin{{equation}}` with proper labels (e.g., `\\label{{eq:example}}`) for cross-referencing.
  * **Prefer concise formulas over verbose text**: Use mathematical notation efficiently to express relationships. Replace lengthy textual explanations with concise, high-value mathematical formulas where possible, while ensuring all symbols and functions are thoroughly explained.
- **CRITICAL - Algorithm Requirements**: The Algorithm subsection must be detailed and step-by-step, including:
  * Variable definitions and data structure specifications
  * **CRITICAL**: Every variable, symbol, and function in the algorithm MUST be clearly defined and explained. All mathematical symbols must have explicit definitions.
  * Explicit input/output specifications with data formats and dimensions for each step
  * Detailed operations with mathematical formulations
  * **CRITICAL**: Every mathematical function, operation, or transformation in the algorithm must have a clear explanation of its purpose, inputs, outputs, and role.
  * Step-by-step execution flow with clear structure
  * Detailed enough for direct implementation
  * **CRITICAL**: Even in algorithm pseudocode, avoid programming function call syntax. Use descriptive statements like "Process the input data" instead of "run(input_data)" or "Execute the transformation" instead of "execute()". Use natural language descriptions of operations, not function/method call notation.
- Express implementation details through mathematical notation or textual descriptions, NOT code parameters
- **CRITICAL - No Programming Function Calls**: NEVER use programming function call syntax or terminology in the text. Avoid expressions like `run()`, `execute()`, `call()`, `invoke()`, `apply()`, `process()`, `compute()`, `forward()`, `backward()`, or any other function/method call notation. Instead, use academic prose to describe operations, such as "the method processes", "the algorithm computes", "the module transforms", "we apply", "the system executes", etc. Academic writing should describe processes using natural language, not programming syntax.
- Extract and synthesize information from all relevant sections (module_blueprints, method_pipeline, etc.)
- Emphasize implementation details, concrete data formats, and step-by-step operations
- **CRITICAL - Concise Text with High-Value Formulas**: Keep text concise and prefer using meaningful mathematical formulas over verbose descriptions. Every formula should be essential and intuitive, with all symbols and functions thoroughly explained.
- Maintain logical flow between modules with smooth transitions
- **CRITICAL - No Arrow Symbols**: NEVER use arrow symbols (→, ->, =>, ⇒, ←, <-, <=, ⇐, etc.) in the text. Use words like "to", "towards", "leads to", "results in", "transforms into", "maps to", etc. instead. Academic writing should use proper prose, not symbols.
- DO NOT include `\\subsection{{Method Pipeline}}` or `\\subsection{{Training and Optimization}}` - these contain experimental implementation details
- Include `\\subsection{{Algorithm}}` wrapped in `\\begin{{algorithm}}` ... `\\end{{algorithm}}` environment, focusing on method execution flow (NOT training details)
- Output the complete LaTeX Methods section wrapped in ```latex ... ``` blocks."""

        async def _attempt(attempt_number: int) -> Optional[Dict[str, Any]]:
            messages = [
                {"role": "system", "content": self.SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ]

            logger.info(
                "MethodsWritingAgent attempt %d (input length=%d chars)",
                attempt_number,
                len(user_content),
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
                "latex_content": latex_content,
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
                "MethodsWritingAgent failed to produce valid LaTeX output after retries."
            )

        return result

