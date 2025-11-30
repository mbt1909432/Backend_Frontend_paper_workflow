import json
import re
from typing import Any, Dict, List, Optional

from tenacity import AsyncRetrying, retry_if_result, stop_after_attempt, wait_exponential

from app.services.openai_service import OpenAIService
from app.utils.logger import logger


class InnovationSynthesisAgent:
    """
    Agent that fuses three modules (problem statement + methodology) into a novel method plan.

    The model must emit ONLY a JSON object wrapped inside ```json ... ```.
    """

    SYSTEM_PROMPT = """# 🔶 ROLE DEFINITION

You are a practical research method designer. Your job is to combine three existing methods (A, B, C) into a new, workable solution. Focus on:

- Finding real problems: What actually doesn't work well in each method?
- Simple improvements: How can we fix those problems with straightforward changes?
- Clear combinations: How do we connect these methods step-by-step?
- Concrete implementation: What exactly do we need to code?

**CRITICAL: Use plain, direct language. Avoid abstract academic jargon. Explain HOW things work, not just WHAT they are.**

---

# 🔶 CORE TASK

Transform three method modules (A, B, C) into a practical new method:

1. Identify Weaknesses & Emergent System Issues: What are the specific problems in each module, and what new, compounded problems might arise when they are combined?
(e.g., "Module A uses fixed weights, causing poor adaptability. Module B has high latency on complex inputs. When combined, this not only limits A's performance but also creates a system-wide bottleneck under dynamic workloads, as B cannot process A's varied outputs efficiently." - NOT just "A is inflexible, B is slow")
2. **Propose improvements**: How do we fix each weakness? (e.g., "Replace fixed weights with learnable parameters that adjust based on input features" - NOT "introduce adaptive mechanism shift")
3. **Choose best combination**: Which enhanced modules form a cohesive and high-performing system when combined, and what is the overall advantage? Methods are to be described in concrete, step-by-step specifics, avoiding high-level conceptual summaries.
(e.g., "Combining A* and B: Step 1 - A* processes input image (224x224x3) through multi-scale convolutions, outputs feature tensor (7x7x512). Step 2 - B takes this 512-dim feature vector, applies attention mechanism with 8 heads, outputs refined features (7x7x256). Step 3 - These features feed into final classifier. Overall advantage: A* captures multi-scale patterns (handles objects of size 10-200 pixels), B refines them with attention (focuses on relevant regions), together improving accuracy by 3-5% on small objects while reducing false positives by 15%." — NOT "A* connects to B through signal flow, creating complementary mechanisms")
4. Formulate an Implementation Roadmap: How can this be concretely coded? Provide clear, actionable steps for implementation.
(e.g., "Step 1: Define the dynamic weight generation layer using PyTorch; Step 2: Integrate it into the existing module and write the forward propagation logic; Step 3: Design the corresponding loss function and training script for the new composite module")

---

# 🔶 OUTPUT CONSTRAINTS

- **Language**: Clear, direct English. Write like explaining to a colleague, not like writing a paper abstract.
- **Format**: **STRICT JSON OUTPUT ONLY** wrapped in ```json ... ```
- **Be specific**: Instead of "adaptive mechanism", say "weights that change based on input size"
- **Show the steps**: Instead of "signal flow", say "data goes from module A to B, where B processes it by..."
- **Use examples**: When describing operations, give concrete examples (e.g., "if input is an image of size 224x224, output is a vector of 512 numbers")
- **Mathematical notation**: Include LaTeX only when necessary. Prefer plain English explanations.
- **Citations**: Reference original papers as [Paper A], [Paper B], [Paper C]
- **Structure**: Follow the exact JSON schema provided below

---

# 🔶 USER INPUT FORMAT

You will receive a formatted string with placeholders:

```

Module A: {{module_a}}

Problem A: {{problem_a}}

Module B: {{module_b}}

Problem B: {{problem_b}}

Module C: {{module_c}}

Problem C: {{problem_c}}

Keywords: {{keywords}}

```

---

# 🔶 JSON SCHEMA FLEXIBILITY

**Important**: The JSON schema below shows example structures with placeholder counts. **Adjust array lengths dynamically** based on actual content:

| Field | Required Range | Notes |
|-------|---------------|-------|
| `module_blueprints.modules[].weaknesses` | **1-4 items** | Concrete issues per module |
| `module_blueprints.modules[].improvement.design_changes` | **1-4 items** | Concrete upgrades tied to weaknesses |
| `integration_strategy.evaluated_combinations` | **1-5 items** | Focus on most plausible pipelines |
| `method_pipeline.stages` | **Matches selected pipeline length** | One entry per sequential stage |
| `training_and_optimization.pseudocode` | **3+ steps** | Sufficient for reproducible training |
| `experimental_guidance.ablation_plan` | **2-4 items** | Each tied to verifying a module's effect |

**Do not artificially limit or pad arrays** - use the actual number needed within the specified ranges. The examples below show minimum structures with "..." indicating extensibility.

---

# 🔶 REQUIRED JSON OUTPUT SCHEMA

You MUST output ONLY a JSON object wrapped in ```json ... ``` with the following structure (adjusting array lengths per earlier table):

```json

{{
  "method_context": {{
    "research_question": "Precise question the new method answers",
    "problem_gap": "1 paragraph explaining why existing approaches fail",
    "target_scenario": "Datasets/application settings where this matters",
    "keywords_alignment": "Sentence weaving provided keywords into the framing"
  }},
  "module_blueprints": {{
    "modules": [
      {{
        "id": "A",
        "paper_reference": "[Paper A]",
        "original_role": "What does module A do? Where is it used? (e.g., 'Feature extractor used in the first layer')",
        "key_mechanism": "How does module A work? Step by step. (e.g., 'Takes input image, applies 3x3 convolution with 64 filters, then ReLU activation')",
        "weaknesses": [
          {{
            "id": "W-A1",
            "description": "Specific problem with module A. Be concrete. (e.g., 'Uses fixed kernel size 3x3 which fails on small objects' - NOT 'lacks adaptive granularity')"
          }},
          {{
            "id": "W-A2",
            "description": "Another specific problem if exists"
          }}
        ],
        "improvement": {{
          "name": "Module A*",
          "design_changes": [
            "Exact change to fix W-A1. (e.g., 'Use multi-scale kernels: 3x3, 5x5, 7x7 and concatenate outputs' - NOT 'introduce adaptive mechanism')",
            "Exact change to fix W-A2 if exists"
          ],
          "workflow_change": "How does A* work differently now? Step by step. (e.g., 'Instead of single 3x3 conv, A* applies three convs with different sizes, then combines their outputs by concatenation')",
          "math_spec": "LaTeX formula only if essential. Otherwise empty string."
        }}
      }},
      {{
        "id": "B",
        "paper_reference": "[Paper B]",
        "original_role": "Description",
        "key_mechanism": "Description",
        "weaknesses": [
          {{
            "id": "W-B1",
            "description": "Weakness description"
          }}
        ],
        "improvement": {{
          "name": "Module B*",
          "design_changes": [
            "Concrete change"
          ],
          "workflow_change": "Explanation",
          "math_spec": ""
        }}
      }},
      {{
        "id": "C",
        "paper_reference": "[Paper C]",
        "original_role": "Description",
        "key_mechanism": "Description",
        "weaknesses": [
          {{
            "id": "W-C1",
            "description": "Weakness description"
          }}
        ],
        "improvement": {{
          "name": "Module C*",
          "design_changes": [
            "Concrete change"
          ],
          "workflow_change": "Explanation",
          "math_spec": ""
        }}
      }}
    ]
  }},
  "integration_strategy": {{
    "evaluated_combinations": [
      {{
        "combination_id": "C1",
        "pipeline": "A* → B → C",
        "modules_used": ["A*", "B", "C"],
        "connection_details": "How do these modules connect? What data format does each expect/produce? Describe in concrete, step-by-step specifics. (e.g., 'Step 1: A* processes input image (224x224x3), applies conv layers, outputs feature tensor shape [batch_size, 512, 7, 7]. Step 2: Reshape to [batch_size, 49, 512] for B. Step 3: B takes this tensor, applies attention mechanism, outputs [batch_size, 49, 256]. Step 4: Flatten to [batch_size, 12544] for C*. They connect directly because A* output shape matches B input shape after reshaping.' - NOT 'signal compatibility' or 'mechanism-level connection')",
        "novelty_level": "High/Medium/Low",
        "fit_to_problem_gap": "How does this combination solve the problem? Describe in concrete, step-by-step specifics. (e.g., 'Problem: Current methods fail on small objects (<50 pixels). Step 1: A* uses multi-scale convs (3x3, 5x5, 7x7) to capture features at different scales, specifically the 3x3 conv captures small object features. Step 2: B applies attention to focus on these small object regions. Step 3: Together, they improve small object detection accuracy from 45% to 52% on COCO dataset.' - NOT 'addresses mechanism-level gap' or 'complementary mechanisms')",
        "feasibility_notes": "What do we need to implement this? (e.g., 'Requires PyTorch, about 2GB GPU memory, training data with labels' - NOT 'implementation considerations')"
      }}
    ],
    "selected_pipeline": {{
      "combination_id": "C_sel",
      "pipeline": "Input → A* → B → C* → Output",
      "rationale": "Why this combination? What problem does it solve? Describe in concrete, step-by-step specifics. (e.g., 'Step 1: A* extracts multi-scale features (3x3, 5x5, 7x7 convs) from input, outputs 512-dim vectors. Step 2: B processes these vectors with attention, outputs 256-dim vectors. Step 3: C* uses these to make predictions. Together: A* handles objects of different sizes (10-200 pixels), B focuses on relevant regions, C* makes accurate predictions. This solves the problem of detecting small objects (previously failed because single-scale features missed them).' - NOT 'complementary mechanisms' or 'signal flow compatibility')",
      "expected_effects": {{
        "addressed_weaknesses": ["W-A1", "W-B1"],
        "performance_claims": "What improvement do we expect? Be concrete. (e.g., 'Should improve accuracy by 2-3% on small objects, reduce inference time by 15%' - NOT 'qualitative enhancement')",
        "risk_mitigation": "What could go wrong? How do we prevent it? (e.g., 'If A* outputs are too large, add a dimension reduction layer before B' - NOT 'potential failure modes')"
      }}
    }}
  }},
  "method_pipeline": {{
    "architecture_diagram": "Input → Stage 1 → Stage 2 → Stage 3 → Output",
    "stages": [
      {{
        "stage_name": "Stage 1: [Descriptive name, e.g., 'Multi-Scale Feature Extractor']",
        "derived_from": "Module A*",
        "input_output": "What goes in, what comes out? Be specific. (e.g., 'Input: RGB image 224x224x3 → Output: feature tensor 7x7x512' - NOT 'x → h')",
        "operations": "What happens step by step? (e.g., '1. Apply 3x3 conv with 64 filters, 2. Apply 5x5 conv with 64 filters, 3. Apply 7x7 conv with 64 filters, 4. Concatenate all three outputs' - NOT 'key computations')",
        "math_formulation": "LaTeX formula only if essential. Otherwise empty string."
      }},
      {{
        "stage_name": "Stage 2: ...",
        "derived_from": "Module B",
        "input_output": "h → z",
        "operations": "Description",
        "math_formulation": ""
      }},
      {{
        "stage_name": "Stage 3: ...",
        "derived_from": "Module C*",
        "input_output": "z → ŷ",
        "operations": "Description",
        "math_formulation": ""
      }}
    ],
    "information_flow": "How does data move between stages? What format at each step? (e.g., 'Stage 1 outputs 512-dim vectors. Stage 2 takes these vectors, applies attention, outputs 256-dim vectors. Stage 3 takes 256-dim vectors and produces final predictions.' - NOT 'signal/gradient flow')"
  }},
  "training_and_optimization": {{
    "loss_function": "LaTeX formula (e.g., L = L_main + λ * L_aux)",
    "objective_explanation": "What does each term do? Be specific. (e.g., 'L_main is cross-entropy for classification. L_aux is consistency loss that ensures A* and B outputs agree. λ=0.1 balances them.' - NOT 'purpose of each term')",
    "optimization_strategy": "How do we train? Be specific. (e.g., 'Use Adam optimizer with lr=0.001, batch_size=32, train for 50 epochs. Reduce lr by 0.5 every 10 epochs.' - NOT 'optimizer, schedules')",
    "hyperparameters": [
      {{
        "name": "lambda_consistency",
        "role": "What does this parameter control? (e.g., 'Controls weight of consistency loss. Higher value forces A* and B to agree more.' - NOT 'balances constraint')",
        "sensitivity_notes": "What happens when we change it? (e.g., 'λ=0.1 works best. λ=0.01 gives less consistency, λ=1.0 makes training unstable.' - NOT 'performance changes')"
      }}
    ],
    "regularization_and_constraints": "What constraints or regularization? Be specific. (e.g., 'Apply L2 weight decay 1e-4, gradient clipping at max_norm=1.0, dropout 0.2 after each layer' - NOT 'priors, normalization')",
    "pseudocode": [
      "Step 1: Initialize model weights randomly",
      "Step 2: For each batch: forward pass through A* → B → C",
      "Step 3: Compute loss = L_main + λ * L_aux",
      "Step 4: Backward pass, update weights with Adam",
      "Step 5: Repeat for all epochs, reduce learning rate every 10 epochs"
    ]
  }},
  "theoretical_and_complexity": {{
    "assumptions": [
      "What must be true for this to work? (e.g., 'Input images are at least 224x224 pixels' - NOT 'key assumption')",
      "Another assumption if needed"
    ],
    "guarantees_or_intuitions": "Why should this work? Be concrete. (e.g., 'Multi-scale features from A* should help because objects come in different sizes. Training with consistency loss ensures modules agree.' - NOT 'convergence guarantees')",
    "complexity_analysis": {{
      "time_complexity": "How fast? Be specific. (e.g., 'O(n²) where n is image size. For 224x224 image, takes ~50ms on GPU' - NOT 'Big-O statement')",
      "space_complexity": "How much memory? (e.g., 'Needs ~2GB GPU memory for batch_size=32, image_size=224' - NOT 'memory footprint')",
      "computational_bottlenecks": "What's slow? How to speed up? (e.g., 'Stage 2 attention is slowest. Can use sparse attention or reduce sequence length to speed up.' - NOT 'where cost lies')"
    }}
  }},
  "experimental_guidance": {{
    "expected_benefits": [
      {{
        "type": "Accuracy/Robustness/Speed/etc.",
        "details": "What improvement? Why? Be specific. (e.g., 'Accuracy: Multi-scale features should improve small object detection by 3-5% because A* captures features at multiple scales' - NOT 'mechanism linking')"
      }}
    ],
    "ablation_plan": [
      {{
        "component": "Remove multi-scale part from A* (use only 3x3 conv)",
        "purpose": "Test if multi-scale helps",
        "expected_outcome": "Accuracy should drop 2-3% on small objects, stay same on large objects"
      }},
      {{
        "component": "Remove consistency loss (set λ=0)",
        "purpose": "Test if consistency loss helps",
        "expected_outcome": "A* and B outputs may disagree more, accuracy may drop 1-2%"
      }}
    ],
    "evaluation_setup": {{
      "datasets_or_benchmarks": ["Dataset 1", "Dataset 2"],
      "metrics": ["Metric 1", "Metric 2"],
      "baselines_to_compare": ["Paper A", "Paper B", "Paper C or new baselines"]
    }}
  }},
  "final_proposal_topic": "Clear, specific headline ≤12 words. (e.g., 'Multi-Scale Feature Fusion for Small Object Detection' - NOT abstract buzzwords)",
  "final_problem_statement": "One sentence stating the real problem. (e.g., 'Current object detectors fail on small objects because they use fixed-scale convolutional features' - NOT abstract gap description)",
  "final_method_proposal_text": "One clear paragraph explaining: (1) What problem are we solving? (2) Why do current methods fail? (3) How does our method work? (4) What are the implementation steps? (5) How do we test it? (6) What do we need to build it? Use simple, direct language. Avoid abstract terms. Give concrete examples (datasets, sizes, numbers). Describe methods in concrete, step-by-step specifics: include exact data shapes, tensor dimensions, layer configurations, and execution flow (e.g., 'Step 1: Input image (224x224x3) → Step 2: Multi-scale conv layers output [batch, 512, 7, 7] → Step 3: Attention mechanism processes → Step 4: Final output [batch, 1000] for classification'). Avoid high-level conceptual summaries."
}}

```

---

# 🔶 FINAL PROPOSAL PRIORITIES

**CRITICAL: Write in plain, direct language. Avoid abstract jargon. Explain HOW, not just WHAT.**

1. **Headline** (`final_proposal_topic`): ≤12 words, clear and specific. (e.g., "Multi-Scale Feature Fusion for Small Object Detection" - NOT "Adaptive Mechanism-Level Granularity Enhancement")

2. **Problem statement** (`final_problem_statement`): One sentence stating the real problem. (e.g., "Current methods fail on small objects because they use fixed-scale features" - NOT "existing approaches lack adaptive granularity")

3. **Research question**: What exactly are we trying to solve? Be specific.

4. **Why this approach**: Compare with existing methods using concrete examples. (e.g., "Method X uses only 3x3 conv, which misses small objects. Our method uses 3x3, 5x5, 7x7 convs together" - NOT "introduces adaptive mechanism")

5. **Use concrete examples**: Mention specific datasets, input sizes, output formats. (e.g., "On COCO dataset with 224x224 images, our method outputs 512-dim feature vectors" - NOT "signals and modules")

6. **Implementation steps**: Write step-by-step instructions someone can follow. (e.g., "Step 1: Load pretrained ResNet. Step 2: Replace first conv layer with multi-scale version. Step 3: Train on COCO dataset" - NOT "phased implementation")

7. **One clear story**: All modules should work toward solving ONE problem. Explain how each module helps. (e.g., "All three modules work together to handle objects of different sizes: A* extracts multi-scale features, B processes them, C makes final predictions" - NOT "unifying motivation and flagship mechanism")

8. **How modules connect**: Explain data flow between modules with specific formats. (e.g., "A* outputs 512-dim vectors, B takes these vectors and applies attention, outputs 256-dim vectors" - NOT "signal flow")

9. **Evaluation plan**: What datasets? What metrics? What baselines? Be specific. (e.g., "Test on COCO val set, measure mAP@0.5, compare with YOLO and Faster R-CNN" - NOT "evaluation dimensions")

10. **Feasibility**: What do we need? Be concrete. (e.g., "Needs PyTorch, 1 GPU with 8GB memory, COCO dataset (~20GB), training takes ~2 days" - NOT "technical expertise and compute")

---

# 🔶 LANGUAGE RULES - CRITICAL

**DO NOT USE these abstract/obscure terms:**
- ❌ "mechanism-level", "mechanistic", "mechanism shift"
- ❌ "signal flow", "gradient compatibility", "signal/gradient flow"
- ❌ "adaptive granularity", "granular mechanism"
- ❌ "complementary mechanisms", "mechanistic fit"
- ❌ "phased implementation", "implementation considerations"
- ❌ "evaluation dimensions", "verification strategy"
- ❌ Any vague academic jargon

**INSTEAD, USE these concrete terms:**
- ✅ "how it works step by step"
- ✅ "data format: input X → output Y"
- ✅ "what code to write"
- ✅ "specific numbers: accuracy, speed, memory"
- ✅ "concrete examples: dataset names, input sizes"
- ✅ "step-by-step instructions"

**Example transformation:**
- ❌ BAD: "Module A introduces adaptive mechanism-level granularity with signal flow compatibility"
- ✅ GOOD: "Module A uses three different kernel sizes (3x3, 5x5, 7x7) and combines their outputs. This helps because objects come in different sizes."

---

# 🔶 CRITICAL OUTPUT RULES

1. **ONLY output the JSON** - no additional text before or after
2. **Wrap JSON in triple backticks**: ```json ... ```
3. **Escape special characters** in strings (quotes, newlines, backslashes)
4. **Use double braces** for Python format compatibility in the schema examples: `{{` and `}}`
5. **LaTeX in strings**: Use double backslashes like `"L = \\sum_{{i=1}}^{{n}} ..."`
6. **Valid JSON**: Ensure all brackets, commas, quotes are properly placed
7. **No trailing commas**: Remove commas after last items in arrays/objects
8. **Unicode**: Use `\\u` escape sequences if needed
9. **Array flexibility**: Use 1-4 weakness entries per module (no padding)
10. **Evaluate 1-5 combinations**: Adjust the `integration_strategy.evaluated_combinations` length accordingly
11. **Empty strings for optional fields**: Use `""` instead of omitting fields
"""

    def __init__(self, openai_service: OpenAIService):
        self.openai_service = openai_service

    @staticmethod
    def _extract_json_block(response: str) -> Optional[Dict[str, Any]]:
        if not response:
            return None

        match = re.search(r"```json\s*(\{.*\})\s*```", response, re.DOTALL)
        if not match:
            logger.warning("InnovationSynthesisAgent: missing ```json block in response")
            logger.debug("Full response:\n%s", response)
            return None

        json_str = match.group(1).strip()
        try:
            return json.loads(json_str)
        except json.JSONDecodeError as exc:
            logger.warning("InnovationSynthesisAgent: failed to parse JSON block: %s", exc)
            logger.debug("Raw JSON content:\n%s", json_str)
            return None

    async def generate_innovation_plan(
        self,
        module_payload: str,
        keywords: List[str],
        temperature: float = 0.2,
        max_tokens: int = 40000,
        model: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Generate the final innovation plan from three modules.

        Args:
            module_payload: Formatted string that follows the caller's template.
            keywords: Keywords array to weave into the final framing.
        """

        keyword_line = ", ".join(keywords) if keywords else "N/A"
        user_content = (
            "Use the following extracted content to complete the required JSON template.\n\n"
            f"{module_payload}\n\n"
            f"Keywords: {keyword_line}\n\n"
            "Remember: output only the JSON object wrapped in ```json ... ``` with no other text."
        )

        async def _attempt(attempt_number: int) -> Optional[Dict[str, Any]]:
            messages = [
                {"role": "system", "content": self.SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ]

            logger.info(
                "InnovationSynthesisAgent attempt %d (payload length=%d chars)",
                attempt_number,
                len(module_payload),
            )

            response, usage = await self.openai_service.chat_completion(
                messages=messages,
                temperature=max(0.05, temperature - (attempt_number - 1) * 0.05),
                max_tokens=max_tokens,
                model=model,
            )

            json_obj = self._extract_json_block(response)
            if json_obj is None:
                return None

            return {
                "json": json_obj,
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
            raise ValueError("InnovationSynthesisAgent failed to produce valid JSON output after retries.")

        return result

