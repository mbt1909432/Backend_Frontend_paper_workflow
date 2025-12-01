from __future__ import annotations

import asyncio
import json
import os
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv

from app.core.agents.experiment_extraction_agent import ExperimentExtractionAgent
from app.core.agents.innovation_synthesis_agent import InnovationSynthesisAgent
from app.core.agents.methodology_extraction_agent import MethodologyExtractionAgent
from app.core.agents.writing.methods_writing_agent import MethodsWritingAgent
from app.services.hot_phrase_service import get_recent_hot_phrases
from app.services.openai_service import OpenAIService
from app.utils.file_manager import save_artifact
from app.utils.logger import logger
from app.config.settings import reload_settings


_KEYWORD_OVERRIDE_LIMIT = 4


def _prepare_keyword_list(raw_keywords: Optional[List[str]]) -> List[str]:
    prepared: List[str] = []
    if not raw_keywords:
        return prepared

    for kw in raw_keywords:
        if not kw:
            continue
        normalized = kw.strip()
        if not normalized:
            continue
        prepared.append(normalized)
        if len(prepared) >= _KEYWORD_OVERRIDE_LIMIT:
            break
    return prepared


@dataclass
class SessionStepInputs:
    """Lightweight container for the data Step 5 & 6 need."""

    session_folder: Path
    generated_dir: Path
    artifact_dir: Path
    markdown_items: List[Dict[str, Any]]
    keywords: List[str]


def load_step_inputs_from_session(session_folder: Path) -> SessionStepInputs:
    """
    Rehydrate the data required by Step 5/6 from a finished session directory.
    """
    session_folder = session_folder.resolve()
    generated_dir = session_folder / "generated"
    artifact_dir = session_folder / "artifact"

    markdown_artifact = artifact_dir / "markdown_emit.json"
    rewrite_artifact = artifact_dir / "rewrite.json"

    if not markdown_artifact.exists():
        raise FileNotFoundError(f"Missing markdown artifact: {markdown_artifact}")
    if not rewrite_artifact.exists():
        raise FileNotFoundError(f"Missing rewrite artifact: {rewrite_artifact}")

    markdown_items = json.loads(markdown_artifact.read_text(encoding="utf-8"))
    rewrite_payload = json.loads(rewrite_artifact.read_text(encoding="utf-8"))

    keywords = rewrite_payload.get("keywords") or rewrite_payload.get("agent_payload", {}).get("keywords") or []

    return SessionStepInputs(
        session_folder=session_folder,
        generated_dir=generated_dir,
        artifact_dir=artifact_dir,
        markdown_items=markdown_items,
        keywords=keywords,
    )


def load_methodology_items_from_artifact(session_folder: Path) -> Tuple[List[Dict[str, Any]], Optional[Path]]:
    """
    Load methodology extraction output from an existing artifact if it exists.
    """
    artifact_path = session_folder / "artifact" / "methodology_extraction.json"
    if not artifact_path.exists():
        return [], None

    artifact_data = json.loads(artifact_path.read_text(encoding="utf-8"))
    return artifact_data.get("methodologies", []) or [], artifact_path


def load_experiment_items_from_artifact(session_folder: Path) -> Tuple[List[Dict[str, Any]], Optional[Path]]:
    """
    Load experiment extraction output from an existing artifact if it exists.
    """
    artifact_path = session_folder / "artifact" / "experiment_extraction.json"
    if not artifact_path.exists():
        return [], None

    artifact_data = json.loads(artifact_path.read_text(encoding="utf-8"))
    return artifact_data.get("experiments", []) or [], artifact_path


async def run_methodology_extraction_step(
    step_inputs: SessionStepInputs,
    methodology_agent: MethodologyExtractionAgent,
    *,
    max_concurrent_tasks: int,
) -> Tuple[Optional[str], List[Dict[str, Any]]]:
    """
    Execute Step 5 (problem statement & methodology extraction) given a prepared context.
    """
    session_folder = step_inputs.session_folder
    methodology_dir = step_inputs.generated_dir / "methodology"
    problem_statement_dir = step_inputs.generated_dir / "problem_statement"
    methodology_dir.mkdir(parents=True, exist_ok=True)
    problem_statement_dir.mkdir(parents=True, exist_ok=True)

    async def extract_single_methodology(idx: int, md_item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        arxiv_id = md_item.get("arxiv_id") or ""
        title = md_item.get("title") or "Untitled"
        markdown_path = md_item.get("markdown_path") or ""

        if not markdown_path:
            logger.warning("Skip methodology extraction for paper #%d: missing markdown_path", idx)
            return None

        md_full_path = session_folder / markdown_path
        if not md_full_path.exists():
            logger.warning("Skip methodology extraction for paper #%d: markdown missing: %s", idx, md_full_path)
            return None

        try:
            md_content = md_full_path.read_text(encoding="utf-8")
        except Exception as exc:
            logger.exception("Failed to read markdown for paper #%d (%s): %s", idx, arxiv_id, exc)
            return None

        # 在后续使用前先清理 markdown：移除纯空行
        # 这样既不影响正文内容，又能避免多余空行干扰后续解析或 token 计数
        md_content = "\n".join(
            line for line in md_content.splitlines() if line.strip()
        )

        extracted_text_marker = "## Extracted Text"
        if extracted_text_marker in md_content:
            parts = md_content.split(extracted_text_marker, 1)
            paper_content = parts[1].strip() if len(parts) > 1 else md_content
        else:
            paper_content = md_content

        if not paper_content or len(paper_content.strip()) < 100:
            logger.warning("Skip methodology extraction for paper #%d: content too short", idx)
            return None

        try:
            extraction_result = await methodology_agent.extract_methodology(
                paper_title=title,
                paper_content=paper_content,
            )

            # 记录本次调用的大模型 token 使用情况，方便排查上下文过长等问题
            usage_stats = extraction_result.get("usage") or {}
            if usage_stats:
                logger.info(
                    "😀Methodology LLM usage for paper #%d (%s): prompt_tokens=%s, completion_tokens=%s, total_tokens=%s",
                    idx,
                    arxiv_id,
                    usage_stats.get("prompt_tokens"),
                    usage_stats.get("completion_tokens"),
                    usage_stats.get("total_tokens"),
                )

            extraction_json = extraction_result.get("json") or {}
            methodology_text = extraction_json.get("methodology", "").strip()
            problem_statement_text = extraction_json.get("problem_statement", "").strip()
            reason = extraction_json.get("reason", "").strip()

            problem_statement_path_rel: Optional[str] = None
            if problem_statement_text:
                problem_statement_filename = f"paper_{idx:02d}_{arxiv_id}_problem_statement.md"
                problem_statement_path = problem_statement_dir / problem_statement_filename
                problem_statement_path.write_text(problem_statement_text, encoding="utf-8")
                problem_statement_path_rel = str(problem_statement_path.relative_to(session_folder))

            if not methodology_text:
                logger.warning("Methodology extraction for paper #%d returned empty methodology", idx)
                return {
                    "index": idx,
                    "arxiv_id": arxiv_id,
                    "title": title,
                    "methodology_path": None,
                    "problem_statement_path": problem_statement_path_rel,
                    "reason": reason,
                    "status": "empty",
                    "usage": extraction_result.get("usage"),
                }

            methodology_filename = f"paper_{idx:02d}_{arxiv_id}_methodology.md"
            methodology_path = methodology_dir / methodology_filename
            methodology_path.write_text(methodology_text, encoding="utf-8")
            rel_methodology_path = methodology_path.relative_to(session_folder)

            logger.info("Methodology extracted for paper #%d (%s): %s", idx, arxiv_id, methodology_path)

            return {
                "index": idx,
                "arxiv_id": arxiv_id,
                "title": title,
                "methodology_path": str(rel_methodology_path),
                "problem_statement_path": problem_statement_path_rel,
                "reason": reason,
                "status": "ok",
                "usage": extraction_result.get("usage"),
            }
        except Exception as exc:
            logger.exception("Failed to extract methodology for paper #%d (%s): %s", idx, arxiv_id, exc)
            return {
                "index": idx,
                "arxiv_id": arxiv_id,
                "title": title,
                "methodology_path": None,
                "problem_statement_path": None,
                "reason": f"Extraction failed: {exc}",
                "status": "failed",
                "usage": None,
            }

    semaphore = asyncio.Semaphore(max_concurrent_tasks)

    async def sem_task(idx: int, md_item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        async with semaphore:
            return await extract_single_methodology(idx, md_item)

    methodology_results = await asyncio.gather(
        *[sem_task(md_item["index"], md_item) for md_item in step_inputs.markdown_items],
        return_exceptions=False,
    )
    methodology_items = [item for item in methodology_results if item is not None]

    artifact_path = save_artifact(
        session_folder=session_folder,
        stage_name="methodology_extraction",
        artifact_data={
            "total_papers": len(step_inputs.markdown_items),
            "extracted_count": len([m for m in methodology_items if m.get("status") == "ok"]),
            "methodologies": methodology_items,
        },
    )
    logger.info("✓ methodology_extraction.json saved at %s", artifact_path)
    return str(artifact_path), methodology_items


async def run_experiment_extraction_step(
    step_inputs: SessionStepInputs,
    experiment_agent: ExperimentExtractionAgent,
    *,
    max_concurrent_tasks: int,
) -> Tuple[Optional[str], List[Dict[str, Any]]]:
    """
    Execute experiment extraction step given a prepared context.
    """
    session_folder = step_inputs.session_folder
    experiment_dir = step_inputs.generated_dir / "experiments"
    experiment_dir.mkdir(parents=True, exist_ok=True)

    async def extract_single_experiment(idx: int, md_item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        arxiv_id = md_item.get("arxiv_id") or ""
        title = md_item.get("title") or "Untitled"
        markdown_path = md_item.get("markdown_path") or ""

        if not markdown_path:
            logger.warning("Skip experiment extraction for paper #%d: missing markdown_path", idx)
            return None

        md_full_path = session_folder / markdown_path
        if not md_full_path.exists():
            logger.warning("Skip experiment extraction for paper #%d: markdown missing: %s", idx, md_full_path)
            return None

        try:
            md_content = md_full_path.read_text(encoding="utf-8")
        except Exception as exc:
            logger.exception("Failed to read markdown for paper #%d (%s): %s", idx, arxiv_id, exc)
            return None

        # 在后续使用前先清理 markdown：移除纯空行
        # 这样既不影响正文内容，又能避免多余空行干扰后续解析或 token 计数
        md_content = "\n".join(
            line for line in md_content.splitlines() if line.strip()
        )

        extracted_text_marker = "## Extracted Text"
        if extracted_text_marker in md_content:
            parts = md_content.split(extracted_text_marker, 1)
            paper_content = parts[1].strip() if len(parts) > 1 else md_content
        else:
            paper_content = md_content

        if not paper_content or len(paper_content.strip()) < 100:
            logger.warning("Skip experiment extraction for paper #%d: content too short", idx)
            return None

        try:
            extraction_result = await experiment_agent.extract_experiments(
                paper_title=title,
                paper_content=paper_content,
            )

            # 记录本次调用的大模型 token 使用情况，方便排查上下文过长等问题
            usage_stats = extraction_result.get("usage") or {}
            if usage_stats:
                logger.info(
                    "😀Experiment LLM usage for paper #%d (%s): prompt_tokens=%s, completion_tokens=%s, total_tokens=%s",
                    idx,
                    arxiv_id,
                    usage_stats.get("prompt_tokens"),
                    usage_stats.get("completion_tokens"),
                    usage_stats.get("total_tokens"),
                )

            extraction_json = extraction_result.get("json") or {}
            experiments_text = extraction_json.get("experiments", "").strip()
            reason = extraction_json.get("reason", "").strip()

            if not experiments_text:
                logger.warning("Experiment extraction for paper #%d returned empty experiments", idx)
                return {
                    "index": idx,
                    "arxiv_id": arxiv_id,
                    "title": title,
                    "experiment_path": None,
                    "reason": reason,
                    "status": "empty",
                    "usage": extraction_result.get("usage"),
                    "agent_payload": extraction_json,
                    "raw_response": extraction_result.get("raw_response"),
                }

            # 将完整 JSON 信息落盘：不仅包含实验正文，还写出 baselines/datasets/metrics 等字段。
            def _format_list_section(items: List[str]) -> str:
                if not items:
                    return "_None_"
                return "\n".join(f"- {entry}" for entry in items)

            experimental_tables = extraction_json.get("experimental_tables", "").strip()
            baselines = extraction_json.get("baselines") or []
            datasets = extraction_json.get("datasets") or []
            metrics = extraction_json.get("metrics") or []
            table_details = extraction_json.get("table_details") or []

            experiment_filename = f"paper_{idx:02d}_{arxiv_id}_experiments.md"
            experiment_path = experiment_dir / experiment_filename

            markdown_sections: List[str] = [
                f"# Experiments - {title}",
                "",
                "## Reason",
                reason or "_Empty_",
                "",
                "## Experiments",
                experiments_text,
                "",
                "## Baselines",
                _format_list_section(baselines),
                "",
                "## Datasets",
                _format_list_section(datasets),
                "",
                "## Metrics",
                _format_list_section(metrics),
                "",
                "## Experimental Tables",
                experimental_tables or "_None_",
                "",
                "## Table Details",
                (
                    "\n\n".join(table_details)
                    if table_details
                    else "_None_"
                ),
                "",
                "## Agent Payload (JSON)",
                "```json",
                json.dumps(extraction_json, ensure_ascii=False, indent=2),
                "```",
            ]
            experiment_path.write_text("\n".join(markdown_sections), encoding="utf-8")
            rel_experiment_path = experiment_path.relative_to(session_folder)

            logger.info("Experiment extracted for paper #%d (%s): %s", idx, arxiv_id, experiment_path)

            return {
                "index": idx,
                "arxiv_id": arxiv_id,
                "title": title,
                "experiment_path": str(rel_experiment_path),
                "reason": reason,
                "status": "ok",
                "usage": extraction_result.get("usage"),
                "agent_payload": extraction_json,
                "raw_response": extraction_result.get("raw_response"),
            }
        except Exception as exc:
            logger.exception("Failed to extract experiment for paper #%d (%s): %s", idx, arxiv_id, exc)
            return {
                "index": idx,
                "arxiv_id": arxiv_id,
                "title": title,
                "experiment_path": None,
                "reason": f"Extraction failed: {exc}",
                "status": "failed",
                "usage": None,
                "agent_payload": None,
                "raw_response": None,
            }

    semaphore = asyncio.Semaphore(max_concurrent_tasks)

    async def sem_task(idx: int, md_item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        async with semaphore:
            return await extract_single_experiment(idx, md_item)

    experiment_results = await asyncio.gather(
        *[sem_task(md_item["index"], md_item) for md_item in step_inputs.markdown_items],
        return_exceptions=False,
    )
    experiment_items = [item for item in experiment_results if item is not None]

    artifact_path = save_artifact(
        session_folder=session_folder,
        stage_name="experiment_extraction",
        artifact_data={
            "total_papers": len(step_inputs.markdown_items),
            "extracted_count": len([e for e in experiment_items if e.get("status") == "ok"]),
            "experiments": experiment_items,
        },
    )
    logger.info("✓ experiment_extraction.json saved at %s", artifact_path)
    return str(artifact_path), experiment_items


async def run_innovation_synthesis_step(
    step_inputs: SessionStepInputs,
    methodology_items: List[Dict[str, Any]],
    innovation_agent: InnovationSynthesisAgent,
    *,
    override_keywords: Optional[List[str]] = None,
    run_count: int = 1,
) -> List[str]:
    """
    Execute Step 6 (innovation synthesis) using the already extracted methodologies.

    Args:
        run_count: How many synthesis attempts to run (≥1). Each run produces
            a separate `innovation_synthesis*.json` artifact.
    """
    if len(methodology_items) < 3:
        logger.warning(
            "Innovation agent skipped: need ≥3 methodology entries, got %d",
            len(methodology_items),
        )
        return []

    session_folder = step_inputs.session_folder
    generated_dir = step_inputs.generated_dir
    eligible_items: List[Dict[str, Any]] = []
    for item in methodology_items:
        if item.get("status") != "ok":
            continue
        methodology_path = item.get("methodology_path")
        problem_path = item.get("problem_statement_path")
        if not methodology_path or not problem_path:
            continue

        methodology_file = session_folder / methodology_path
        problem_file = session_folder / problem_path
        if not methodology_file.exists() or not problem_file.exists():
            continue

        try:
            methodology_text = methodology_file.read_text(encoding="utf-8").strip()
            problem_text = problem_file.read_text(encoding="utf-8").strip()
        except Exception as exc:
            logger.warning(
                "Skip innovation entry for paper #%s due to read error: %s",
                item.get("index"),
                exc,
            )
            continue

        if not methodology_text or not problem_text:
            continue

        eligible_items.append(
            {
                "paper_index": item["index"],
                "arxiv_id": item.get("arxiv_id"),
                "title": item.get("title"),
                "methodology_text": methodology_text,
                "problem_text": problem_text,
            }
        )

    if len(eligible_items) < 3:
        logger.warning(
            "Innovation agent skipped: only %d eligible entries with both methodology and problem statement.",
            len(eligible_items),
        )
        return []

    def _build_module_payload() -> Tuple[str, List[Dict[str, Any]]]:
        selected = random.sample(eligible_items, 3) if len(eligible_items) > 3 else eligible_items

        module_lines: List[str] = []
        metadata: List[Dict[str, Any]] = []
        for offset, item in enumerate(selected):
            module_id = chr(ord("A") + offset)
            title = item.get("title") or f"Paper {module_id}"
            arxiv_id = item.get("arxiv_id") or ""
            module_lines.append(f"Module {module_id}: [{title} | {arxiv_id}]\n{item['methodology_text']}")
            module_lines.append("")
            module_lines.append(f"Problem {module_id}: [{title} | {arxiv_id}]\n{item['problem_text']}")
            module_lines.append("")
            metadata.append(
                {
                    "module_id": module_id,
                    "paper_index": item["paper_index"],
                    "arxiv_id": arxiv_id,
                    "title": title,
                }
            )

        return "\n".join(module_lines).strip(), metadata

    keyword_override = _prepare_keyword_list(override_keywords)
    hot_keyword_candidates: List[str] = []
    if not keyword_override:
        hot_keyword_candidates = get_recent_hot_phrases(limit=_KEYWORD_OVERRIDE_LIMIT)
        keyword_override = _prepare_keyword_list(hot_keyword_candidates)
        if keyword_override:
            logger.info(
                "Using %d hot phrases from DB as innovation keywords override.",
                len(keyword_override),
            )

    keywords_for_agent = keyword_override or step_inputs.keywords
    if keyword_override:
        logger.info(
            "Innovation agent using %d user-supplied keywords instead of rewrite output.",
            len(keyword_override),
        )

    try:
        run_count = max(1, run_count)
        final_proposal_dir = generated_dir / "final_proposals"
        final_proposal_dir.mkdir(parents=True, exist_ok=True)

        async def run_single_innovation(run_index: int) -> str:
            """Execute a single innovation synthesis run and return artifact path."""
            module_payload, selection_metadata = _build_module_payload()
            logger.info(
                "Innovation run %d/%d: sending payload to agent (modules=%d, keywords=%d, payload_chars=%d)",
                run_index + 1,
                run_count,
                len(selection_metadata),
                len(keywords_for_agent),
                len(module_payload),
            )
            innovation_result = await innovation_agent.generate_innovation_plan(
                module_payload=module_payload,
                keywords=keywords_for_agent,
            )
            usage_stats = innovation_result.get("usage") or {}
            logger.info(
                "Innovation run %d/%d: agent call finished (prompt_tokens=%s, completion_tokens=%s)",
                run_index + 1,
                run_count,
                usage_stats.get("prompt_tokens"),
                usage_stats.get("completion_tokens"),
            )
            stage_suffix = "" if run_index == 0 else f"_{run_index + 1}"
            artifact_path = save_artifact(
                session_folder=session_folder,
                stage_name=f"innovation_synthesis{stage_suffix}",
                artifact_data={
                    "run_index": run_index + 1,
                    "selected_modules": selection_metadata,
                    "module_payload": module_payload,
                    "keywords": keywords_for_agent,
                    "hot_keywords": keyword_override if hot_keyword_candidates else [],
                    "output": innovation_result.get("json"),
                    "usage": innovation_result.get("usage"),
                },
            )

            # 读取该 artifact，拼接 final_proposal_topic / final_problem_statement / final_method_proposal_text
            try:
                artifact_file = Path(artifact_path)
                if not artifact_file.exists():
                    logger.warning(
                        "Skip final proposal markdown: artifact missing at %s",
                        artifact_file,
                    )
                else:
                    artifact_payload = json.loads(artifact_file.read_text(encoding="utf-8"))
                    output = artifact_payload.get("output") or {}
                    topic = (output.get("final_proposal_topic") or "").strip()
                    problem = (output.get("final_problem_statement") or "").strip()
                    method_text = (output.get("final_method_proposal_text") or "").strip()

                    if not (topic or problem or method_text):
                        logger.info(
                            "Skip final proposal markdown: missing required fields in %s",
                            artifact_file,
                        )
                    else:
                        md_filename = f"{artifact_file.stem}.md"
                        md_path = final_proposal_dir / md_filename

                        lines: List[str] = []
                        # 标题
                        lines.append(f"# {topic or 'Final Proposal'}")
                        lines.append("")
                        # 问题描述
                        if problem:
                            lines.append("## Problem Statement")
                            lines.append("")
                            lines.append(problem)
                            lines.append("")
                        # 方法方案
                        if method_text:
                            lines.append("## Method Proposal")
                            lines.append("")
                            lines.append(method_text)
                            lines.append("")

                        md_path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
                        rel_md_path = md_path.relative_to(session_folder)
                        logger.info(
                            "Final proposal markdown generated: %s (from %s)",
                            md_path,
                            artifact_file,
                        )
            except Exception as md_exc:
                logger.exception(
                    "Failed to build final proposal markdown for run #%d: %s",
                    run_index + 1,
                    md_exc,
                )
            logger.info(
                "✓ innovation_synthesis%s.json saved at %s",
                stage_suffix or "",
                artifact_path,
            )
            return str(artifact_path)

        # 并行执行所有 runs
        artifact_paths = await asyncio.gather(
            *[run_single_innovation(run_index) for run_index in range(run_count)],
            return_exceptions=False,
        )
        return artifact_paths
    except Exception as exc:
        logger.exception("Innovation agent failed: %s", exc)
        return []


def _find_innovation_synthesis_artifacts(session_folder: Path) -> List[Path]:
    """
    Find all innovation_synthesis*.json artifacts in the session's artifact directory.
    """
    artifact_dir = session_folder / "artifact"
    if not artifact_dir.exists():
        return []
    
    # Find all innovation_synthesis*.json files
    pattern = "innovation_synthesis*.json"
    artifacts = sorted(artifact_dir.glob(pattern))
    return artifacts


async def run_methods_writing_step(
    step_inputs: SessionStepInputs,
    methods_writing_agent: MethodsWritingAgent,
    *,
    temperature: float = 0.7,
    max_tokens: int = 20000,
) -> List[str]:
    """
    Execute Step 7 (Methods writing) using the innovation_synthesis artifacts.
    
    This step reads all innovation_synthesis*.json artifacts and generates
    LaTeX Methods sections for each one.
    
    Args:
        step_inputs: Session inputs containing session folder and paths
        methods_writing_agent: Initialized MethodsWritingAgent instance
        temperature: Generation temperature (default: 0.7)
        max_tokens: Maximum tokens for generation (default: 20000)
    
    Returns:
        List of artifact paths for the generated methods_writing*.json files
    """
    session_folder = step_inputs.session_folder
    generated_dir = step_inputs.generated_dir
    methods_dir = generated_dir / "methods"
    methods_dir.mkdir(parents=True, exist_ok=True)
    
    innovation_artifacts = _find_innovation_synthesis_artifacts(session_folder)
    
    if not innovation_artifacts:
        logger.warning(
            "Methods writing step skipped: no innovation_synthesis*.json artifacts found in %s",
            session_folder / "artifact",
        )
        return []
    
    logger.info(
        "Found %d innovation_synthesis artifact(s), generating Methods sections...",
        len(innovation_artifacts),
    )
    
    async def generate_single_methods(artifact_path: Path, run_index: int) -> Optional[str]:
        """Generate Methods section for a single innovation_synthesis artifact."""
        try:
            artifact_data = json.loads(artifact_path.read_text(encoding="utf-8"))
            innovation_json = artifact_data.get("output")
            
            if not innovation_json:
                logger.warning(
                    "Skip methods writing for %s: missing 'output' field",
                    artifact_path.name,
                )
                return None
            
            logger.info(
                "Methods writing run %d/%d: processing %s",
                run_index + 1,
                len(innovation_artifacts),
                artifact_path.name,
            )
            
            methods_result = await methods_writing_agent.generate_methods_section(
                innovation_json=innovation_json,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            
            usage_stats = methods_result.get("usage") or {}
            logger.info(
                "Methods writing run %d/%d: agent call finished (prompt_tokens=%s, completion_tokens=%s, total_tokens=%s)",
                run_index + 1,
                len(innovation_artifacts),
                usage_stats.get("prompt_tokens"),
                usage_stats.get("completion_tokens"),
                usage_stats.get("total_tokens"),
            )
            
            latex_content = methods_result.get("latex_content", "").strip()
            if not latex_content:
                logger.warning(
                    "Methods writing run %d/%d: empty LaTeX content from agent",
                    run_index + 1,
                    len(innovation_artifacts),
                )
                return None
            
            # Save LaTeX content to file
            latex_filename = f"{artifact_path.stem}_methods.tex"
            latex_path = methods_dir / latex_filename
            latex_path.write_text(latex_content, encoding="utf-8")
            rel_latex_path = latex_path.relative_to(session_folder)
            logger.info(
                "Methods LaTeX saved: %s (from %s)",
                latex_path,
                artifact_path.name,
            )
            
            # Determine stage suffix based on artifact name
            artifact_stem = artifact_path.stem
            if artifact_stem == "innovation_synthesis":
                stage_suffix = ""
            else:
                # Extract suffix from innovation_synthesis_2 -> _2
                suffix = artifact_stem.replace("innovation_synthesis", "")
                stage_suffix = suffix if suffix else ""
            
            # Save artifact
            methods_artifact_path = save_artifact(
                session_folder=session_folder,
                stage_name=f"methods_writing{stage_suffix}",
                artifact_data={
                    "run_index": run_index + 1,
                    "source_innovation_artifact": str(artifact_path.relative_to(session_folder)),
                    "latex_path": str(rel_latex_path),
                    "latex_content": latex_content,
                    "raw_response": methods_result.get("raw_response"),
                    "usage": usage_stats,
                },
            )
            
            logger.info(
                "✓ methods_writing%s.json saved at %s",
                stage_suffix or "",
                methods_artifact_path,
            )
            
            return str(methods_artifact_path)
            
        except Exception as exc:
            logger.exception(
                "Failed to generate Methods section for %s: %s",
                artifact_path.name,
                exc,
            )
            return None
    
    # Process all artifacts sequentially (to avoid overwhelming the API)
    artifact_paths: List[str] = []
    for idx, artifact_path in enumerate(innovation_artifacts):
        result = await generate_single_methods(artifact_path, idx)
        if result:
            artifact_paths.append(result)
    
    return artifact_paths




def _load_local_env_file(env_filename: Optional[str] = None) -> Optional[Path]:
    """
    Load a local .env file located in this folder for quick manual testing.
    """
    base_dir = Path(__file__).resolve().parent
    seen: List[Path] = []

    explicit_name = env_filename or os.environ.get("POSTPROCESS_ENV_FILE")
    if explicit_name:
        seen.append(base_dir / explicit_name)
    seen.extend(
        [
            base_dir / ".env.postprocess",
            base_dir / ".env",
        ]
    )

    for env_path in seen:
        if env_path.exists():
            load_dotenv(env_path, override=True)
            reload_settings()
            logger.info("Loaded postprocess env from %s", env_path)
            return env_path

    logger.info(
        "No local env file found for postprocess_steps (checked %s)",
        ", ".join(str(path) for path in seen),
    )
    return None


async def main_run_steps_5_and_6(
    custom_keywords: Optional[List[str]] = None,
    innovation_run_count: int = 1,
) -> None:
    """
    测试入口：对指定 session 依次运行 Step 5（Methodology）和 Step 6（Innovation）。
    """

    # TODO: 修改为真实 session 路径，例如 Path("E:/.../session_20251128_xxx")
    test_session_folder = Path(r"E:\pycharm_project\software_idea\academic draft agentic_workflow\app\core\workflows\output\dev_tester\session_20251128_214503_52fb8e1e").resolve()
    max_concurrent_tasks = 2

    _load_local_env_file()

    step_inputs = load_step_inputs_from_session(test_session_folder)

    openai_service = OpenAIService()
    methodology_agent = MethodologyExtractionAgent(openai_service=openai_service)
    experiment_agent = ExperimentExtractionAgent(openai_service=openai_service)
    innovation_agent = InnovationSynthesisAgent(openai_service=openai_service)

    (methodology_artifact, methodology_items), (experiment_artifact, experiment_items) = await asyncio.gather(
        run_methodology_extraction_step(
        step_inputs=step_inputs,
        methodology_agent=methodology_agent,
        max_concurrent_tasks=max_concurrent_tasks,
        ),
        run_experiment_extraction_step(
            step_inputs=step_inputs,
            experiment_agent=experiment_agent,
            max_concurrent_tasks=max_concurrent_tasks,
        ),
    )

    logger.info("Methodology artifact: %s", methodology_artifact)
    logger.info("Experiment artifact: %s", experiment_artifact)

    if not methodology_items:
        logger.info("No methodology items extracted; skip innovation synthesis.")
        return

    innovation_artifacts = await run_innovation_synthesis_step(
        step_inputs=step_inputs,
        methodology_items=methodology_items,
        innovation_agent=innovation_agent,
        override_keywords=custom_keywords,
        run_count=innovation_run_count,
    )

    if innovation_artifacts:
        logger.info("Innovation artifacts: %s", innovation_artifacts)
    else:
        logger.info("Innovation synthesis skipped or failed.")


async def main_run_step_6_only(
    custom_keywords: Optional[List[str]] = None,
    innovation_run_count: int = 1,
) -> None:
    """
    测试入口：复用已有 methodology_extraction.json，仅运行 Step 6（Innovation）。
    """

    # TODO: 修改为真实 session 路径，例如 Path("E:/.../session_20251128_xxx")
    test_session_folder = Path(r"E:\pycharm_project\software_idea\academic draft agentic_workflow\app\core\workflows\output\dev_tester\session_20251128_224959_6a932f9b").resolve()

    _load_local_env_file()

    step_inputs = load_step_inputs_from_session(test_session_folder)
    methodology_items, _ = load_methodology_items_from_artifact(step_inputs.session_folder)

    if not methodology_items:
        logger.warning("No methodology artifact found or empty; cannot run Step 6.")
        return

    openai_service = OpenAIService()
    innovation_agent = InnovationSynthesisAgent(openai_service=openai_service)

    innovation_artifacts = await run_innovation_synthesis_step(
        step_inputs=step_inputs,
        methodology_items=methodology_items,
        innovation_agent=innovation_agent,
        override_keywords=custom_keywords,
        run_count=innovation_run_count,
    )

    if innovation_artifacts:
        logger.info("Innovation artifacts: %s", innovation_artifacts)
    else:
        logger.info("Innovation synthesis skipped or failed.")


async def main_run_step_7_only(
    temperature: float = 0.7,
    max_tokens: int = 20000,
) -> None:
    """
    测试入口：复用已有 innovation_synthesis*.json，仅运行 Step 7（Methods Writing）。
    """

    # TODO: 修改为真实 session 路径，例如 Path("E:/.../session_20251128_xxx")
    test_session_folder = Path(r"E:\pycharm_project\software_idea\academic draft agentic_workflow\app\core\workflows\output\2025_11_30\session_20251130_152450_2e84a1cc").resolve()

    _load_local_env_file()

    step_inputs = load_step_inputs_from_session(test_session_folder)

    openai_service = OpenAIService()
    methods_writing_agent = MethodsWritingAgent(openai_service=openai_service)

    methods_artifacts = await run_methods_writing_step(
        step_inputs=step_inputs,
        methods_writing_agent=methods_writing_agent,
        temperature=temperature,
        max_tokens=max_tokens,
    )

    if methods_artifacts:
        logger.info("Methods writing artifacts: %s", methods_artifacts)
    else:
        logger.info("Methods writing skipped or failed.")


if __name__ == "__main__":
    _load_local_env_file()
    asyncio.run(main_run_step_7_only())
    #asyncio.run(main_run_step_6_only())
