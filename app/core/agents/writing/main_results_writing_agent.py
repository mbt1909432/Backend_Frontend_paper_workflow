import json
import re
from typing import Any, Dict, List, Optional

from tenacity import AsyncRetrying, retry_if_result, stop_after_attempt, wait_exponential

from app.services.openai_service import OpenAIService
from app.utils.logger import logger


class MainResultsWritingAgent:
    """
    Agent responsible for composing the full experimental section as LaTeX,
    including experimental settings, main results (tables + narrative),
    and ablation studies, following a fixed NeurIPS-style template.
    """

    SYSTEM_PROMPT = """Main_Results_Writing_Prompt (Primary instructions for Experiment section authoring)

1. Role Definition
- You are an elite reviewer-level AI assistant (NeurIPS / ICLR / ICML / CVPR / ACL caliber).
- You fully understand state-of-the-art experimental writing standards, baseline curation, dataset alignment, evaluation metrics, and LaTeX table craft. 

2. Core Task
Given experiments retrieved from top-k papers (each includes baselines, datasets, metrics, and optional raw tables) and the method proposal for our work, you must:
- Choose realistic, domain-appropriate benchmarks, datasets, metrics, baselines, and ablation variants inspired by the retrieved experiments.
- Generate LaTeX-ready tables with realistic, self-consistent numbers where our method is best yet plausibly so.
- Author the entire Experiment section (settings, main results, ablation) strictly following the template below.

3. Input Assumptions
- Experiments arrive as {experiment1}, {experiment2}, {experiment3}, each summarizing a retrieved paper's experimental details. Count may vary but examples focus on three.
- Method proposal is sourced from the upstream Innovation Synthesis Agent; expect fields like final_proposal_topic, final_problem_statement, final_method_proposal_text, method_pipeline, and experimental_guidance.
- Optional constraints describe formatting requirements (± std, bolding rules, table ordering, significance tests, etc.).

4. Output Contract (STRICT)
You MUST output a single LaTeX block that exactly follows the structure below, **wrapped inside a single ```latex ... ``` fenced code block**, with no extra commentary before or after. Replace bracketed placeholders (e.g., [YOUR METHOD]) with concrete content grounded in the provided experiments, method proposal, and innovation plan. Keep the section and subsection titles, labels, and overall layout unchanged.

```latex
\\section{Experiment}

\\label{sec:experiment}

% Opening overview (2-3 sentences)
In this section, we demonstrate the effectiveness of [YOUR METHOD] by addressing [NUMBER] key questions: (1) [QUESTION 1]? (2) [QUESTION 2]? (3) [QUESTION 3]?

\\subsection{Experimental Settings}

\\label{subsec:exp_settings}

\\noindent\\textbf{Benchmarks.}
We evaluate our model on [BENCHMARK CATEGORY] benchmarks. 
For [TASK TYPE 1], we report detailed results on [BENCHMARK 1]~\\cite{ref1}, [BENCHMARK 2]~\\cite{ref2}, and [BENCHMARK 3]~\\cite{ref3}.
For [TASK TYPE 2], we conduct evaluations on [BENCHMARK 4]~\\cite{ref4} and [BENCHMARK 5]~\\cite{ref5}.
[Add 1-2 sentence descriptions for each major benchmark as needed.]

\\noindent\\textbf{Implementation Details.}
We [train/fine-tune] [BASE MODEL]~\\cite{ref} on the [DATASET] using [FRAMEWORK/LIBRARY].
The training is conducted on [HARDWARE SPECS] for a total of [NUMBER] steps, implemented with [ADDITIONAL FRAMEWORK].
The training configuration includes a group size of [NUMBER], a learning rate of [NUMBER], and [NUMBER] epochs.
The sample size of [DESCRIPTION] is set to [NUMBER].
During evaluation, we adopt [EVALUATION STRATEGY].
Additional implementation details are provided in Appendix~\\ref{app:implementation}.

\\subsection{Main Results}

\\label{subsec:main_results}

% Overview paragraph (2-3 sentences)
We present the results of [YOUR METHOD] across [BENCHMARK CATEGORIES] (Table~\\ref{tab:main_results}), [ADDITIONAL EVALUATIONS] (Table~\\ref{tab:additional}), and [POST-TRAINING EVALUATIONS] (Fig.~\\ref{fig:results}), showing [KEY FINDING PREVIEW].
A detailed analysis is provided below.

\\noindent\\textbf{Performance on [BENCHMARK CATEGORY 1].}
As shown in Table~\\ref{tab:main_results}, [YOUR METHOD] delivers [KEY FINDING] on [SPECIFIC BENCHMARKS].
For instance, on the widely adopted [BENCHMARK NAME] benchmark for [TASK TYPE], [YOUR METHOD] achieves [METRIC VALUE], [COMPARISON WITH BASELINES].
Compared with [BASELINE MODEL] using only [BASELINE APPROACH], [YOUR METHOD] shows [IMPROVEMENT DESCRIPTION].
[Add additional comparative results and analysis as needed.]
These results demonstrate that [IMPLICATIONS].

\\begin{table*}[t!]
\\centering
\\caption{[DESCRIPTION OF WHAT THE TABLE SHOWS]}
\\label{tab:main_results}
\\begin{tabular}{l|ccc|ccc}
\\toprule
\\textbf{Method} & \\textbf{Metric 1} & \\textbf{Metric 2} & \\textbf{Metric 3} & \\textbf{Metric 4} & \\textbf{Metric 5} & \\textbf{Metric 6} \\\\
\\midrule
Baseline 1~\\cite{ref} & 00.0 & 00.0 & 00.0 & 00.0 & 00.0 & 00.0 \\\\
Baseline 2~\\cite{ref} & 00.0 & 00.0 & 00.0 & 00.0 & 00.0 & 00.0 \\\\
Baseline 3~\\cite{ref} & 00.0 & 00.0 & 00.0 & 00.0 & 00.0 & 00.0 \\\\
\\midrule
\\textbf{Ours} & \\textbf{00.0} & \\textbf{00.0} & \\textbf{00.0} & \\textbf{00.0} & \\textbf{00.0} & \\textbf{00.0} \\\\
\\bottomrule
\\end{tabular}
\\end{table*}

\\noindent\\textbf{Performance on [BENCHMARK CATEGORY 2].}
[Similar structure as above - table reference, key finding, numerical evidence, comparison, implications]

\\noindent\\textbf{[Additional Result Category if needed].}
To assess [SPECIFIC ASPECT], [DESCRIBE EXPERIMENT].
As shown in Fig.~\\ref{fig:results}, [DESCRIBE FINDINGS].
[Additional analysis and implications.]

\\begin{figure}[t!]
\\centering
\\includegraphics[width=0.8\\linewidth]{figures/results.pdf}
\\caption{[DESCRIPTION OF WHAT THE FIGURE SHOWS]}
\\label{fig:results}
\\end{figure}

\\subsection{Ablation Study}

\\label{subsec:ablation}

% Overview paragraph (2-3 sentences)
In this section, we conduct ablation studies to systematically evaluate the contribution of [COMPONENTS/DESIGN CHOICES] in [YOUR METHOD].
Specifically, we examine [NUMBER] ablated variants: (1) [VARIANT 1 DESCRIPTION]; (2) [VARIANT 2 DESCRIPTION]; and (3) [VARIANT 3 DESCRIPTION].
[Optional: describe experimental setup if different from main results.]
The corresponding results are reported in Table~\\ref{tab:ablation}.

\\begin{table*}[t!]
\\centering
\\caption{[DESCRIPTION OF ABLATION STUDY]}
\\label{tab:ablation}
\\begin{tabular}{l|ccc}
\\toprule
\\textbf{Variant} & \\textbf{Metric 1} & \\textbf{Metric 2} & \\textbf{Metric 3} \\\\
\\midrule
Full Model & \\textbf{00.0} & \\textbf{00.0} & \\textbf{00.0} \\\\
w/o Component 1 & 00.0 & 00.0 & 00.0 \\\\
w/o Component 2 & 00.0 & 00.0 & 00.0 \\\\
w/o Component 3 & 00.0 & 00.0 & 00.0 \\\\
\\bottomrule
\\end{tabular}
\\end{table*}

\\noindent\\textbf{[Ablation Theme 1].}
[Describe findings for first ablation component with numerical support and implications.]

\\noindent\\textbf{[Ablation Theme 2].}
[Describe findings for second ablation component with numerical support and implications.]

\\noindent\\textbf{[Ablation Theme 3].}
[Describe findings for third ablation component with numerical support and implications.]
```

5. Critical Constraints
- Align benchmark choices, datasets, metrics, baselines, and ablation variants with the retrieved experiments and method proposal; justify any necessary extensions plausibly.
- Keep numbers realistic and self-consistent across all tables and narrative; ensure that averages and comparisons are coherent.
- Use the provided method name consistently as the primary row in tables and in the text (replace [YOUR METHOD]).
- Never mention “experiment1/2/3” in the output; synthesize them into a unified story.
- Do NOT change section/subsection titles, labels, or the LaTeX structure; only replace bracketed placeholders with grounded content.

6. Tone & Style
- Mirror SOTA conference writing: confident, precise, non-exaggerated.
- Use active voice, formal tone, and data-backed claims.

7. Output Format
- Output the complete LaTeX Experiment section wrapped in a single ```latex ... ``` fenced code block. Do not include any other text outside the code block.
"""

    def __init__(self, openai_service: OpenAIService):
        self.openai_service = openai_service

    @staticmethod
    def _normalize_experiments(experiment_sections: List[str]) -> List[Dict[str, Any]]:
        normalized: List[Dict[str, Any]] = []
        for idx, raw_section in enumerate(experiment_sections, start=1):
            if not raw_section:
                continue
            normalized.append(
                {
                    "id": idx,
                    "content": raw_section.strip(),
                }
            )
        if not normalized:
            raise ValueError("At least one experiment section is required.")
        return normalized

    @staticmethod
    def _validate_method_metadata(our_method: Dict[str, Any]) -> None:
        if not our_method:
            raise ValueError("our_method metadata is required.")
        if not our_method.get("full_name"):
            raise ValueError("our_method.full_name is required.")

    def _build_user_prompt(
        self,
        experiment_sections: List[str],
        method_proposal: str,
        our_method: Dict[str, Any],
        innovation_plan: Optional[Dict[str, Any]] = None,
    ) -> str:
        experiments_payload = self._normalize_experiments(experiment_sections)
        self._validate_method_metadata(our_method)

        payload: Dict[str, Any] = {
            "experiments": experiments_payload,
            "method_proposal": method_proposal.strip(),
            "our_method": our_method,
        }
        if innovation_plan:
            payload["innovation_plan"] = innovation_plan

        payload_text = json.dumps(payload, ensure_ascii=False, indent=2)
        reminder = """Remember:
- Satisfy all four output components in order.
- Use the provided method name for our method consistently in every table row.
- When innovation_plan is present, ground descriptions in its fields (final_proposal_topic/name, final_problem_statement, final_method_proposal_text, method_context, method_pipeline.stages, experimental_guidance.evaluation_setup, experimental_guidance.expected_benefits, experimental_guidance.ablation_plan, integration_strategy.selected_pipeline.expected_effects, integration_strategy.expected_effects).
- Keep numbers realistic and cross-table consistent; align dataset/metric naming with the experiments.
- Use theoretical_and_complexity.complexity_analysis (time/space/bottlenecks) plus training_and_optimization specifics to justify efficiency, stability, and robustness claims whenever available.
- Justify dataset/metric choices with method_context (research_question/problem_gap/target_scenario) and align task coverage with method_pipeline stages.
- Use ± std formatting only when it keeps the narrative consistent; otherwise stay concise.
- Cross-reference tables exactly via the requested \\label keys (main_results, dataset_specific, efficiency, generalization, robustness, significance).
- If statistical significance is unnecessary, explicitly state "Not required" in Task Structure, skip the table, and omit the paragraph.
"""
        return f"{payload_text}\n\n{reminder}"

    @staticmethod
    def _extract_latex_block(response: str) -> Optional[str]:
        """
        Extract LaTeX content from response wrapped in ```latex ... ``` blocks.

        This mirrors the behavior of MethodsWritingAgent so that downstream code
        can rely on receiving a clean LaTeX snippet without Markdown fences.
        """
        try:
            latex_pattern = r"```latex\s*\n?(.*?)\n?```"
            match = re.search(latex_pattern, response, re.DOTALL)
            if match:
                content = match.group(1).strip()
                logger.debug(
                    "MainResultsWritingAgent: extracted latex block (length=%d chars)",
                    len(content),
                )
                return content

            # Fallback: any fenced code block
            code_block_pattern = r"```\w*\s*\n?(.*?)```"
            code_match = re.search(code_block_pattern, response, re.DOTALL)
            if code_match:
                logger.warning(
                    "MainResultsWritingAgent: no ```latex block found, using generic code block"
                )
                return code_match.group(1).strip()

            logger.warning(
                "MainResultsWritingAgent: missing ```latex block in response"
            )
            logger.debug("Full response (truncated):\n%s", response[:1000])
            return None
        except Exception as exc:
            logger.warning(
                "MainResultsWritingAgent: failed to extract LaTeX block: %s", exc
            )
            logger.debug("Full response (truncated):\n%s", response[:1000])
            return None

    async def generate_main_results_package(
        self,
        experiment_sections: List[str],
        method_proposal: str,
        our_method: Dict[str, Any],
        *,
        innovation_plan: Optional[Dict[str, Any]] = None,
        temperature: float = 0.6,
        max_tokens: int = 40000,
        model: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Generate the Main Results package (baseline selection, task structure, tables, narrative).
        """

        user_content = self._build_user_prompt(
            experiment_sections=experiment_sections,
            method_proposal=method_proposal,
            our_method=our_method,
            innovation_plan=innovation_plan,
        )

        async def _attempt(attempt_number: int) -> Optional[Dict[str, Any]]:
            messages = [
                {"role": "system", "content": self.SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ]
            logger.info(
                "MainResultsWritingAgent attempt %d (payload chars=%d)",
                attempt_number,
                len(user_content),
            )
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
                    "MainResultsWritingAgent: empty response from chat_completion"
                )
                return None

            latex_content = self._extract_latex_block(response)
            if latex_content is None or "\\section{Experiment}" not in latex_content:
                logger.warning(
                    "MainResultsWritingAgent: failed to extract valid LaTeX Experiment section"
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
            raise ValueError("MainResultsWritingAgent failed to produce a valid response after retries.")

        return result


__all__ = ["MainResultsWritingAgent"]

