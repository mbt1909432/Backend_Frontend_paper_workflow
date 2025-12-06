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
- Author the entire Experiment section (settings, main results, case study, ablation) strictly following the template below.
- **For Main Results subsection: Generate AT LEAST 4-5 paragraphs total, including 2-3 "Performance on [DATASET]" paragraphs and 2-3 paragraphs on model capabilities beyond dataset performance (e.g., training reward scores, trajectory quality, generation quality). All paragraphs MUST integrate and synthesize insights from {experiment1}, {experiment2}, {experiment3} by combining their experimental findings, baseline comparisons, evaluation metrics, and capability assessments into a unified narrative. Never mention "experiment1/2/3" explicitly in the output.**
- **For Case Study subsection: Generate AT LEAST 2-3 paragraphs total, each focusing on a different dimension/aspect of case study (e.g., scenario-based analysis, task-specific analysis, performance analysis, behavior analysis, comparative analysis, failure analysis). Each paragraph MUST follow this structure: (1) Start by explicitly stating what this case study aims to demonstrate/showcase; (2) Then present detailed case study analysis with specific examples, observations, or qualitative/quantitative evidence; (3) Finally, conclude with key findings/implications derived from the case study.**
- For ablation studies, design BOTH high-level component removals (w/o module A/B/C) AND low-level implementation detail variants (hyperparameters, architectural choices, training strategies) by carefully analyzing design choices in the retrieved papers. Reference these papers when explaining why specific low-level variants were considered and how they differ from our approach.

3. Input Assumptions
- Experiments arrive as {experiment1}, {experiment2}, {experiment3}, each summarizing a retrieved paper's experimental details. Count may vary but examples focus on three.
- Method proposal is sourced from the upstream Innovation Synthesis Agent; expect fields like final_proposal_topic, final_problem_statement, final_method_proposal_text, method_pipeline, and experimental_guidance.
- Optional constraints describe formatting requirements (± std, bolding rules, table ordering, significance tests, etc.).

4. Output Contract (STRICT)
You MUST output a single LaTeX block that exactly follows the structure below, **wrapped inside a single ```latex ... ``` fenced code block**, with no extra commentary before or after. Replace bracketed placeholders (e.g., [YOUR METHOD]) with concrete content grounded in the provided experiments, method proposal, and innovation plan. Keep the section and subsection titles, labels, and overall layout unchanged. The Experiment section MUST include: Experimental Settings, Main Results, Case Study, and Ablation Study subsections in that order.

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

% CRITICAL: Main Results subsection MUST contain AT LEAST 4-5 paragraphs total:
% - 2-3 paragraphs for "Performance on [DATASET/BENCHMARK]" (dataset performance evaluation)
% - 2-3 paragraphs for model capabilities beyond dataset performance (e.g., training reward scores, trajectory quality, generation quality, convergence behavior, robustness characteristics, etc.)
% - All paragraphs must integrate insights from {experiment1}, {experiment2}, {experiment3} by synthesizing their experimental findings, baseline comparisons, and evaluation metrics

\\noindent\\textbf{Performance on [BENCHMARK CATEGORY 1].}
As shown in Table~\\ref{tab:main_results}, [YOUR METHOD] delivers [KEY FINDING] on [SPECIFIC BENCHMARKS].
For instance, on the widely adopted [BENCHMARK NAME] benchmark for [TASK TYPE], [YOUR METHOD] achieves [METRIC VALUE], [COMPARISON WITH BASELINES].
Compared with [BASELINE MODEL] using only [BASELINE APPROACH], [YOUR METHOD] shows [IMPROVEMENT DESCRIPTION].
[Integrate insights from {experiment1}, {experiment2}, {experiment3}: synthesize their experimental findings, baseline comparisons, evaluation metrics, and dataset-specific observations. Add additional comparative results and analysis as needed.]
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
[Similar structure as above - table reference, key finding, numerical evidence, comparison, implications. Integrate insights from {experiment1}, {experiment2}, {experiment3} by synthesizing their experimental findings, baseline comparisons, and evaluation metrics.]

\\noindent\\textbf{Performance on [BENCHMARK CATEGORY 3] (Optional - if 3rd dataset performance paragraph is needed).}
[Similar structure as above - table reference, key finding, numerical evidence, comparison, implications. Integrate insights from {experiment1}, {experiment2}, {experiment3} by synthesizing their experimental findings, baseline comparisons, and evaluation metrics.]

\\noindent\\textbf{[Model Capabilities Beyond Dataset Performance - e.g., Training Dynamics and Reward Scores].}
Beyond standard benchmark performance, we evaluate [YOUR METHOD]'s capabilities in [SPECIFIC ASPECT, e.g., training reward scores, trajectory quality, convergence behavior].
To assess [SPECIFIC ASPECT], [DESCRIBE EXPERIMENT AND METHODOLOGY].
As shown in Fig.~\\ref{fig:results} [or Table~\\ref{tab:additional}], [DESCRIBE FINDINGS WITH NUMERICAL EVIDENCE].
[Compare with baselines or expected behavior, integrating insights from {experiment1}, {experiment2}, {experiment3} by synthesizing their findings on similar capability evaluations, training dynamics, or quality metrics.]
These results demonstrate that [YOUR METHOD] exhibits [KEY CAPABILITY FINDINGS], indicating [IMPLICATIONS FOR MODEL BEHAVIOR OR QUALITY].

\\noindent\\textbf{[Additional Model Capabilities - e.g., Trajectory Quality or Generation Quality].}
To further assess [YOUR METHOD]'s capabilities beyond dataset metrics, we examine [SPECIFIC ASPECT, e.g., generated trajectory quality, sample diversity, robustness characteristics].
[DESCRIBE EXPERIMENTAL SETUP AND EVALUATION METHODOLOGY].
As shown in [Table~\\ref{tab:additional} or Fig.~\\ref{fig:results}], [DESCRIBE FINDINGS WITH SPECIFIC METRICS AND NUMERICAL EVIDENCE].
[Compare with baselines or theoretical expectations, integrating insights from {experiment1}, {experiment2}, {experiment3} by synthesizing their findings on similar capability evaluations, quality assessments, or robustness analyses.]
These findings reveal that [YOUR METHOD] demonstrates [KEY CAPABILITY FINDINGS], suggesting [IMPLICATIONS FOR PRACTICAL DEPLOYMENT OR MODEL UNDERSTANDING].

\\begin{figure}[t!]
\\centering
\\includegraphics[width=0.8\\linewidth]{figures/results.pdf}
\\caption{[DESCRIPTION OF WHAT THE FIGURE SHOWS]}
\\label{fig:results}
\\end{figure}

\\subsection{Case Study}

\\label{subsec:case_study}

% Overview paragraph (1-2 sentences)
In this section, we conduct case studies to provide deeper insights into [YOUR METHOD]'s behavior and effectiveness across [2-3 DIMENSIONS, e.g., different scenarios, task types, or evaluation perspectives].

% CRITICAL: Case Study subsection MUST contain AT LEAST 2-3 paragraphs total:
% - Each paragraph focuses on a different dimension/aspect of case study
% - Each paragraph structure: (1) Start by stating what this case study aims to demonstrate/showcase; (2) Then present detailed case study analysis with specific examples, observations, or qualitative/quantitative evidence; (3) Finally, conclude with key findings/implications derived from the case study

\\noindent\\textbf{[Case Study Dimension 1 - e.g., Scenario-based Analysis or Task-specific Analysis].}
[First paragraph structure: (1) Start by explicitly stating what this case study aims to demonstrate/showcase (e.g., "This case study aims to demonstrate how [YOUR METHOD] handles [SPECIFIC SCENARIO/TASK TYPE] by examining [SPECIFIC EXAMPLES OR INSTANCES]." or "To showcase [YOUR METHOD]'s effectiveness in [SPECIFIC DIMENSION], we analyze [SPECIFIC CASE STUDY EXAMPLES]."); (2) Then present detailed case study analysis - describe specific examples, instances, or scenarios; provide qualitative observations, quantitative evidence, or visual/behavioral patterns observed in the case study; compare with baselines or expected behavior if relevant; (3) Finally, conclude with key findings/implications derived from this case study (e.g., "These case studies reveal that [YOUR METHOD] [KEY FINDING], indicating [IMPLICATIONS]." or "The analysis demonstrates that [YOUR METHOD] [KEY FINDING], suggesting [IMPLICATIONS].").]

\\noindent\\textbf{[Case Study Dimension 2 - e.g., Performance Analysis or Behavior Analysis].}
[Second paragraph structure: (1) Start with a transition word/phrase (e.g., "Next,", "Furthermore,", "Additionally,") to connect with the previous paragraph, then explicitly state what this case study aims to demonstrate/showcase (e.g., "Next, we examine [YOUR METHOD]'s behavior in [ANOTHER DIMENSION] through case studies on [SPECIFIC EXAMPLES]."); (2) Present detailed case study analysis with specific examples, observations, or evidence; (3) Conclude with key findings/implications. Example opening: "Next, to showcase [YOUR METHOD]'s [SPECIFIC CAPABILITY] in [SPECIFIC CONTEXT], we conduct case studies on [SPECIFIC EXAMPLES]."]

\\noindent\\textbf{[Case Study Dimension 3 - e.g., Comparative Analysis or Failure Analysis (Optional)].}
[Third paragraph structure (if needed): (1) Start with a transition word/phrase (e.g., "Additionally,", "Moreover,", "We also", "Finally,") to connect with previous paragraphs, then explicitly state what this case study aims to demonstrate/showcase; (2) Present detailed case study analysis; (3) Conclude with key findings/implications. Example opening: "Additionally, we conduct case studies to examine [YOUR METHOD]'s [SPECIFIC ASPECT] by analyzing [SPECIFIC EXAMPLES]."]

\\subsection{Ablation Study}

\\label{subsec:ablation}

% Overview paragraph (structured format)
In this section, we conduct ablation studies to systematically evaluate the contribution of each core component in [YOUR METHOD].
Specifically, we examine 4-5 ablated variants: (1) our method w/o module A (high-level: component removal), which [EXPLANATION OF HOW THIS VARIANT WORKS - describe what is removed/replaced and how the system functions without it]; (2) our method w/o module B (high-level: component removal), which [EXPLANATION OF HOW THIS VARIANT WORKS - describe what is removed/replaced and how the system functions without it]; (3) [LOW-LEVEL VARIANT 1: e.g., our method with alternative hyperparameter X=Y instead of X=Z, inspired by [REFERENCE TO RETRIEVED PAPER]], which [EXPLANATION - describe the alternative design choice and why it was considered]; (4) [LOW-LEVEL VARIANT 2: e.g., our method with alternative architectural choice Y instead of Z, inspired by [REFERENCE TO RETRIEVED PAPER]], which [EXPLANATION - describe the alternative design choice and why it was considered]; and (5) [OPTIONAL FIFTH VARIANT: either high-level or low-level, with appropriate explanation].
[Optional: describe experimental setup if different from main results.]
The corresponding results are reported in Table~\\ref{tab:ablation1}, Table~\\ref{tab:ablation2}, Table~\\ref{tab:ablation3}, Table~\\ref{tab:ablation4}, and Fig.~\\ref{fig:ablation}.

\\begin{table*}[t!]
\\centering
\\caption{[DESCRIPTION OF ABLATION STUDY 1 - e.g., High-level Component Removal Analysis]}
\\label{tab:ablation1}
\\begin{tabular}{l|ccc}
\\toprule
\\textbf{Variant} & \\textbf{Metric 1} & \\textbf{Metric 2} & \\textbf{Metric 3} \\\\
\\midrule
Full Model & \\textbf{00.0} & \\textbf{00.0} & \\textbf{00.0} \\\\
w/o Component 1 (High-level) & 00.0 & 00.0 & 00.0 \\\\
w/o Component 2 (High-level) & 00.0 & 00.0 & 00.0 \\\\
\\bottomrule
\\end{tabular}
\\end{table*}

\\begin{table*}[t!]
\\centering
\\caption{[DESCRIPTION OF ABLATION STUDY 2 - e.g., High-level Component Removal Analysis]}
\\label{tab:ablation2}
\\begin{tabular}{l|ccc}
\\toprule
\\textbf{Variant} & \\textbf{Metric 1} & \\textbf{Metric 2} & \\textbf{Metric 3} \\\\
\\midrule
Full Model & \\textbf{00.0} & \\textbf{00.0} & \\textbf{00.0} \\\\
w/o Component 3 (High-level) & 00.0 & 00.0 & 00.0 \\\\
[Additional high-level variant if needed] & 00.0 & 00.0 & 00.0 \\\\
\\bottomrule
\\end{tabular}
\\end{table*}

\\begin{table*}[t!]
\\centering
\\caption{[DESCRIPTION OF ABLATION STUDY 3 - e.g., Low-level Implementation Detail Analysis]}
\\label{tab:ablation3}
\\begin{tabular}{l|ccc}
\\toprule
\\textbf{Variant} & \\textbf{Metric 1} & \\textbf{Metric 2} & \\textbf{Metric 3} \\\\
\\midrule
Full Model & \\textbf{00.0} & \\textbf{00.0} & \\textbf{00.0} \\\\
Variant 1 (Low-level: [DESCRIPTION]) & 00.0 & 00.0 & 00.0 \\\\
Variant 2 (Low-level: [DESCRIPTION]) & 00.0 & 00.0 & 00.0 \\\\
\\bottomrule
\\end{tabular}
\\end{table*}

\\begin{table*}[t!]
\\centering
\\caption{[DESCRIPTION OF ABLATION STUDY 4 - e.g., Low-level Implementation Detail Analysis]}
\\label{tab:ablation4}
\\begin{tabular}{l|ccc}
\\toprule
\\textbf{Variant} & \\textbf{Metric 1} & \\textbf{Metric 2} & \\textbf{Metric 3} \\\\
\\midrule
Full Model & \\textbf{00.0} & \\textbf{00.0} & \\textbf{00.0} \\\\
Variant 3 (Low-level: [DESCRIPTION]) & 00.0 & 00.0 & 00.0 \\\\
Variant 4 (Low-level: [DESCRIPTION]) & 00.0 & 00.0 & 00.0 \\\\
[Optional fifth variant] & 00.0 & 00.0 & 00.0 \\\\
\\bottomrule
\\end{tabular}
\\end{table*}

\\begin{figure}[t!]
\\centering
\\includegraphics[width=0.8\\linewidth]{figures/ablation.pdf}
\\caption{[DESCRIPTION OF ABLATION FIGURE - e.g., visualization of component contributions, performance trends, etc.]}
\\label{fig:ablation}
\\end{figure}

\\noindent\\textbf{[Ablation Theme 1 - High-level: Component Removal].}
[First paragraph structure: (1) Start by stating the purpose of this paragraph - what this ablation aims to evaluate/understand (e.g., "The purpose of this ablation is to evaluate the contribution of module A by examining how the system performs when this component is removed." or "This paragraph examines the impact of removing module A on overall performance."); (2) Then analyze the numerical results from Table~\\ref{tab:ablation1} - cite specific numbers, compare performance drops/gains, discuss trends across metrics/datasets; (3) Finally, conclude with the key finding/implication (e.g., "These results demonstrate that module A is crucial for [specific functionality], as its removal leads to [X%] performance degradation.").]

\\noindent\\textbf{[Ablation Theme 2 - High-level: Component Removal].}
[Second paragraph structure: (1) Start with a transition word/phrase (e.g., "Next,", "Furthermore,", "Additionally,") to connect with the previous paragraph; (2) State what this ablation evaluates; (3) Analyze numerical results from Table~\\ref{tab:ablation2} with specific citations; (4) Conclude with key findings. Example opening: "Next, we examine the contribution of module B by removing it from our method."]

\\noindent\\textbf{[Ablation Theme 3 - Low-level: Implementation Detail].}
[Third paragraph structure: (1) Start with a transition word/phrase (e.g., "Further,", "Additionally,", "Moreover,") to connect with previous paragraphs; (2) State what this low-level ablation evaluates (e.g., alternative hyperparameter settings, architectural choices inspired by retrieved papers); (3) Reference relevant design choices from retrieved papers when applicable; (4) Analyze numerical results from Table~\\ref{tab:ablation3} with specific citations; (5) Conclude with key findings about why this implementation detail matters. Example opening: "Further, we investigate the impact of [specific low-level design choice] by comparing our default setting with alternative configurations inspired by [retrieved paper]."]

\\noindent\\textbf{[Ablation Theme 4 - Low-level: Implementation Detail].}
[Fourth paragraph structure: (1) Start with a transition word/phrase (e.g., "Additionally,", "Moreover,", "We also") to connect with previous paragraphs; (2) State what this low-level ablation evaluates; (3) Reference relevant design choices from retrieved papers when applicable; (4) Analyze numerical results from Table~\\ref{tab:ablation4} with specific citations; (5) Conclude with key findings. Example opening: "Additionally, we explore the effect of [another low-level design choice] by examining alternative implementations."]

\\noindent\\textbf{[Ablation Theme 5 - Low-level: Implementation Detail (Optional)].}
[Fifth paragraph structure (if needed): (1) Start with a transition word/phrase (e.g., "Finally,", "Moreover,", "We further") to connect with previous paragraphs; (2) State what this ablation evaluates; (3) Reference relevant design choices from retrieved papers when applicable; (4) Analyze numerical results from Table~\\ref{tab:ablation4} (or create Table~\\ref{tab:ablation5} if a fifth table is needed) with specific citations; (5) Conclude with key findings. Example opening: "Finally, we conduct a sensitivity analysis on [specific parameter/component] to understand its impact on performance."]
```

5. Critical Constraints
- Align benchmark choices, datasets, metrics, baselines, and ablation variants with the retrieved experiments and method proposal; justify any necessary extensions plausibly.
- Keep numbers realistic and self-consistent across all tables and narrative; ensure that averages and comparisons are coherent.
- Use the provided method name consistently as the primary row in tables and in the text (replace [YOUR METHOD]).
- Never mention “experiment1/2/3” in the output; synthesize them into a unified story.
- Do NOT change section/subsection titles, labels, or the LaTeX structure; only replace bracketed placeholders with grounded content.
- For the Ablation Study subsection overview, strictly follow this format: (1) Start with "In this section, we conduct ablation studies to systematically evaluate the contribution of each core component in [YOUR METHOD]."; (2) Then state "Specifically, we examine 4-5 ablated variants:"; (3) List each variant as "our method w/o module X, which [EXPLANATION]" where the explanation describes what is removed/replaced and how the system functions without that module; (4) End with "The corresponding results are reported in Table~\\ref{tab:ablation1}, Table~\\ref{tab:ablation2}, Table~\\ref{tab:ablation3}, Table~\\ref{tab:ablation4}, and Fig.~\\ref{fig:ablation}." (include figure reference if ablation figure exists, otherwise just mention the tables).
- **CRITICAL: You MUST generate AT LEAST 4 ablation tables** (Table~\\ref{tab:ablation1}, Table~\\ref{tab:ablation2}, Table~\\ref{tab:ablation3}, Table~\\ref{tab:ablation4}). Each table should focus on a different ablation theme or dimension. The tables can be organized as follows: (1) Table~\\ref{tab:ablation1} - High-level component removal analysis (e.g., w/o module A, w/o module B); (2) Table~\\ref{tab:ablation2} - Additional high-level component removal analysis (e.g., w/o module C, or other high-level variants); (3) Table~\\ref{tab:ablation3} - Low-level implementation detail analysis (e.g., hyperparameter variants, architectural choices); (4) Table~\\ref{tab:ablation4} - Additional low-level implementation detail analysis (e.g., training strategy variants, sensitivity analysis). You may add Table~\\ref{tab:ablation5} if a fifth table is needed for additional analysis.
- For the Ablation Study subsection, you MUST include BOTH high-level and low-level ablation analyses:
  * High-level ablations (2-3 variants): Remove or replace entire modules/components (e.g., "w/o module A", "w/o module B"). These demonstrate the contribution of major architectural components. These should be presented in Table~\\ref{tab:ablation1} and/or Table~\\ref{tab:ablation2}.
  * Low-level ablations (2-3 variants): Examine fine-grained implementation details inspired by retrieved papers, such as: (a) alternative hyperparameter settings (e.g., learning rates, batch sizes, temperature parameters); (b) different architectural choices within modules (e.g., attention mechanisms, activation functions, normalization strategies); (c) alternative training strategies (e.g., loss formulations, optimization schedules, data augmentation); (d) sensitivity analyses for key design parameters; (e) sub-component contributions within a module. When describing low-level ablations, explicitly reference relevant design choices from the retrieved papers (experiments) that inspired these variants, explaining why these alternatives were considered and how they differ from our approach. These should be presented in Table~\\ref{tab:ablation3} and/or Table~\\ref{tab:ablation4}.
- Generate 4-5 ablation paragraphs total, ensuring a balanced mix of high-level component removals and low-level implementation detail analyses. Each paragraph should provide numerical evidence from the corresponding ablation table (Table~\\ref{tab:ablation1}, Table~\\ref{tab:ablation2}, Table~\\ref{tab:ablation3}, or Table~\\ref{tab:ablation4}) and explain the implications of the findings.
- For ablation paragraphs structure: (1) The FIRST paragraph must start by explicitly stating its purpose/what it aims to evaluate (e.g., "The purpose of this ablation is to evaluate..." or "This paragraph examines..."), then analyze numerical results from Table~\\ref{tab:ablation1} with specific citations, and conclude with key findings; (2) The SECOND paragraph must begin with a transition word/phrase and analyze Table~\\ref{tab:ablation2}; (3) The THIRD paragraph must begin with a transition word/phrase and analyze Table~\\ref{tab:ablation3}; (4) The FOURTH paragraph must begin with a transition word/phrase and analyze Table~\\ref{tab:ablation4}; (5) All SUBSEQUENT paragraphs (if a 5th paragraph is needed) must begin with a transition word/phrase (e.g., "Next,", "Furthermore,", "Additionally,", "Moreover,", "We also", "Finally,") to create smooth flow and connect different ablation analyses together, then follow the same structure: state purpose, analyze table data, conclude with findings.
- **CRITICAL: For Main Results subsection, you MUST generate AT LEAST 4-5 paragraphs total:**
  * **2-3 paragraphs** must be "Performance on [DATASET/BENCHMARK]" paragraphs that evaluate dataset performance. Each paragraph should: (1) Reference a specific table (e.g., Table~\\ref{tab:main_results}); (2) Present key findings with numerical evidence; (3) Compare with baselines; (4) Integrate insights from {experiment1}, {experiment2}, {experiment3} by synthesizing their experimental findings, baseline comparisons, evaluation metrics, and dataset-specific observations; (5) Conclude with implications.
  * **2-3 paragraphs** must focus on model capabilities beyond dataset performance, such as: (a) training dynamics and reward scores; (b) trajectory quality or generation quality; (c) convergence behavior; (d) sample diversity; (e) robustness characteristics; (f) other domain-specific capabilities. Each paragraph should: (1) State what capability is being evaluated; (2) Describe experimental setup and methodology; (3) Present findings with numerical evidence from figures or tables; (4) Compare with baselines or theoretical expectations; (5) Integrate insights from {experiment1}, {experiment2}, {experiment3} by synthesizing their findings on similar capability evaluations, training dynamics, quality metrics, or robustness analyses; (6) Conclude with implications for model behavior, practical deployment, or model understanding.
  * All paragraphs must synthesize content from {experiment1}, {experiment2}, {experiment3} rather than simply listing them separately. Never mention "experiment1/2/3" explicitly in the output; instead, integrate their insights into a unified narrative.
- **CRITICAL: For Case Study subsection, you MUST generate AT LEAST 2-3 paragraphs total:**
  * Each paragraph must focus on a different dimension/aspect of case study, such as: (a) scenario-based analysis (examining how the method handles different scenarios or contexts); (b) task-specific analysis (analyzing performance on specific task types or instances); (c) performance analysis (deep dive into specific performance characteristics); (d) behavior analysis (examining model behavior patterns or decision-making processes); (e) comparative analysis (comparing method behavior across different conditions or settings); (f) failure analysis (analyzing failure cases or edge cases); (g) other domain-specific case study dimensions.
  * Each paragraph MUST strictly follow this structure: (1) **Start by explicitly stating what this case study aims to demonstrate/showcase** (e.g., "This case study aims to demonstrate how [YOUR METHOD] handles [SPECIFIC SCENARIO] by examining [SPECIFIC EXAMPLES]." or "To showcase [YOUR METHOD]'s effectiveness in [SPECIFIC DIMENSION], we analyze [SPECIFIC CASE STUDY EXAMPLES]."); (2) **Then present detailed case study analysis** - describe specific examples, instances, or scenarios; provide qualitative observations, quantitative evidence, or visual/behavioral patterns observed in the case study; compare with baselines or expected behavior if relevant; (3) **Finally, conclude with key findings/implications** derived from this case study (e.g., "These case studies reveal that [YOUR METHOD] [KEY FINDING], indicating [IMPLICATIONS]." or "The analysis demonstrates that [YOUR METHOD] [KEY FINDING], suggesting [IMPLICATIONS].").
  * Paragraphs should be connected with transition words/phrases (e.g., "Next,", "Furthermore,", "Additionally,", "Moreover,", "We also", "Finally,") to create smooth flow between different case study dimensions.
- In the Main Results subsection, integrate and extend the comparison dimensions inspired by the retrieved related work (e.g., datasets, metrics, settings, robustness/efficiency axes), so that our method is contrasted against baselines along deeper and multi-dimensional experimental axes, and its advantages are linked to clear theoretical or methodological justifications.
- Strengthen the Experiment overview and subsection overviews by posing deeper guiding questions that probe mechanisms, boundary conditions, and fundamental research issues (rather than only listing which module works better), and make sure these questions are explicitly connected to the subsequent experimental design and findings.
- **CRITICAL: Mathematical Equations Format**: All mathematical equations MUST use `\begin{equation} ... \end{equation}` environment. NEVER use `$$ ... $$`, `\[ ... \]`, or `\( ... \)` for displayed equations. Inline math can use `$ ... $` or `\( ... \)`, but displayed equations must use `\begin{equation}` with proper labels (e.g., `\label{eq:example}`) for cross-referencing.
- **CRITICAL: Coding Content Restriction**: Coding-related content (e.g., code snippets, function calls, API usage, programming syntax, implementation code, pseudocode with programming constructs) MUST ONLY appear in the "Implementation Details" paragraph within the "Experimental Settings" subsection. ALL other sections and subsections (Main Results, Case Study, Ablation Study, and any other paragraphs) MUST NOT contain any coding-related content. Use academic language and natural descriptions instead of code-like expressions throughout the rest of the Experiment section.
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
- Cross-reference tables exactly via the requested \\label keys (main_results, dataset_specific, efficiency, generalization, robustness, significance, ablation1, ablation2, ablation3, ablation4).
- If statistical significance is unnecessary, explicitly state "Not required" in Task Structure, skip the table, and omit the paragraph.
- **CRITICAL: Mathematical Equations Format**: All displayed mathematical equations MUST use `\\begin{equation} ... \\end{equation}` environment. NEVER use `$$ ... $$`, `\\[ ... \\]`, or `\\( ... \\)` for displayed equations. Inline math can use `$ ... $` or `\\( ... \\)`, but displayed equations must use `\\begin{equation}` with proper labels (e.g., `\\label{eq:example}`) for cross-referencing.
- **CRITICAL: Coding Content Restriction**: Coding-related content (e.g., code snippets, function calls, API usage, programming syntax, implementation code, pseudocode with programming constructs) MUST ONLY appear in the "Implementation Details" paragraph within the "Experimental Settings" subsection. ALL other sections and subsections (Main Results, Case Study, Ablation Study, and any other paragraphs) MUST NOT contain any coding-related content. Use academic language and natural descriptions instead of code-like expressions throughout the rest of the Experiment section.
- **CRITICAL: For Main Results subsection, you MUST generate AT LEAST 4-5 paragraphs total:**
  * **2-3 paragraphs** must be "Performance on [DATASET/BENCHMARK]" paragraphs that evaluate dataset performance. Each paragraph must integrate insights from {experiment1}, {experiment2}, {experiment3} by synthesizing their experimental findings, baseline comparisons, evaluation metrics, and dataset-specific observations. Never mention "experiment1/2/3" explicitly; synthesize their insights into a unified narrative.
  * **2-3 paragraphs** must focus on model capabilities beyond dataset performance (e.g., training reward scores, trajectory quality, generation quality, convergence behavior, sample diversity, robustness characteristics). Each paragraph must integrate insights from {experiment1}, {experiment2}, {experiment3} by synthesizing their findings on similar capability evaluations, training dynamics, quality metrics, or robustness analyses. Never mention "experiment1/2/3" explicitly; synthesize their insights into a unified narrative.
- **CRITICAL: For Case Study subsection, you MUST generate AT LEAST 2-3 paragraphs total:**
  * Each paragraph must focus on a different dimension/aspect of case study (e.g., scenario-based analysis, task-specific analysis, performance analysis, behavior analysis, comparative analysis, failure analysis).
  * Each paragraph MUST follow this structure: (1) Start by explicitly stating what this case study aims to demonstrate/showcase (e.g., "This case study aims to demonstrate..." or "To showcase [YOUR METHOD]'s effectiveness in [DIMENSION], we analyze..."); (2) Then present detailed case study analysis with specific examples, observations, or qualitative/quantitative evidence; (3) Finally, conclude with key findings/implications derived from the case study (e.g., "These case studies reveal that..." or "The analysis demonstrates that...").
  * Use transition words/phrases (e.g., "Next,", "Furthermore,", "Additionally,", "Moreover,", "We also", "Finally,") to connect paragraphs.
- **CRITICAL: For Ablation Study, you MUST generate AT LEAST 4 tables** (Table~\\ref{tab:ablation1}, Table~\\ref{tab:ablation2}, Table~\\ref{tab:ablation3}, Table~\\ref{tab:ablation4}). Each table should focus on a different ablation theme: Table~\\ref{tab:ablation1} and Table~\\ref{tab:ablation2} for high-level component removals, Table~\\ref{tab:ablation3} and Table~\\ref{tab:ablation4} for low-level implementation details. You may add Table~\\ref{tab:ablation5} if needed.
- For Ablation Study overview: Start with "In this section, we conduct ablation studies to systematically evaluate the contribution of each core component in [YOUR METHOD]." Then list 4-5 variants as "our method w/o module X, which [EXPLANATION]" where explanation describes what is removed/replaced and how the system functions without it. End with references to Table~\\ref{tab:ablation1}, Table~\\ref{tab:ablation2}, Table~\\ref{tab:ablation3}, Table~\\ref{tab:ablation4}, and Fig.~\\ref{fig:ablation}.
- For Ablation Study paragraphs: Generate 4-5 ablation paragraphs that include BOTH high-level (2-3 variants: component/module removals) AND low-level (2-3 variants: implementation details like hyperparameters, architectural choices, training strategies inspired by retrieved papers). When describing low-level ablations, explicitly reference design choices from the retrieved experiments/papers that inspired these variants. Each paragraph should provide numerical evidence from the corresponding table (Table~\\ref{tab:ablation1}, Table~\\ref{tab:ablation2}, Table~\\ref{tab:ablation3}, or Table~\\ref{tab:ablation4}) and explain implications. IMPORTANT: (1) The FIRST paragraph must start by explicitly stating its purpose/what it aims to evaluate, then analyze Table~\\ref{tab:ablation1} data with specific citations, and conclude with findings; (2) The SECOND paragraph must begin with a transition word/phrase and analyze Table~\\ref{tab:ablation2}; (3) The THIRD paragraph must begin with a transition word/phrase and analyze Table~\\ref{tab:ablation3}; (4) The FOURTH paragraph must begin with a transition word/phrase and analyze Table~\\ref{tab:ablation4}; (5) All SUBSEQUENT paragraphs (if a 5th paragraph is needed) must begin with a transition word/phrase (e.g., "Next,", "Furthermore,", "Additionally,", "Moreover,", "We also", "Finally,") to create smooth flow between paragraphs, then follow the same structure: state purpose, analyze table data, conclude with findings.
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

        last_response: Optional[str] = None
        last_usage: Optional[Dict[str, Any]] = None

        async def _attempt(attempt_number: int) -> Optional[Dict[str, Any]]:
            nonlocal last_response, last_usage
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

            # 保存最后一次响应
            last_response = response
            last_usage = usage

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

        # 如果所有重试都失败，但最后一次有响应，直接保存整个响应为.tex
        if result is None and last_response:
            logger.warning(
                "MainResultsWritingAgent: all retries failed, saving full response as .tex file"
            )
            return {
                "content": last_response,
                "raw_response": last_response,
                "usage": last_usage or {},
            }

        if result is None:
            raise ValueError("MainResultsWritingAgent failed to produce a valid response after retries.")

        return result


__all__ = ["MainResultsWritingAgent"]

