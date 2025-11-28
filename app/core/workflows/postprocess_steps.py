from __future__ import annotations

import asyncio
import json
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.core.agents.innovation_synthesis_agent import InnovationSynthesisAgent
from app.core.agents.methodology_extraction_agent import MethodologyExtractionAgent
from app.utils.file_manager import save_artifact
from app.utils.logger import logger


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


async def run_innovation_synthesis_step(
    step_inputs: SessionStepInputs,
    methodology_items: List[Dict[str, Any]],
    innovation_agent: InnovationSynthesisAgent,
) -> Optional[str]:
    """
    Execute Step 6 (innovation synthesis) using the already extracted methodologies.
    """
    if len(methodology_items) < 3:
        logger.warning(
            "Innovation agent skipped: need ≥3 methodology entries, got %d",
            len(methodology_items),
        )
        return None

    session_folder = step_inputs.session_folder
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
        return None

    selected_items = random.sample(eligible_items, 3) if len(eligible_items) > 3 else eligible_items

    module_lines: List[str] = []
    selection_metadata: List[Dict[str, Any]] = []
    for offset, item in enumerate(selected_items):
        module_id = chr(ord("A") + offset)
        title = item.get("title") or f"Paper {module_id}"
        arxiv_id = item.get("arxiv_id") or ""
        module_lines.append(f"Module {module_id}: [{title} | {arxiv_id}]\n{item['methodology_text']}")
        module_lines.append("")
        module_lines.append(f"Problem {module_id}: [{title} | {arxiv_id}]\n{item['problem_text']}")
        module_lines.append("")
        selection_metadata.append(
            {
                "module_id": module_id,
                "paper_index": item["paper_index"],
                "arxiv_id": arxiv_id,
                "title": title,
            }
        )

    module_payload = "\n".join(module_lines).strip()

    try:
        innovation_result = await innovation_agent.generate_innovation_plan(
            module_payload=module_payload,
            keywords=step_inputs.keywords,
        )
    except Exception as exc:
        logger.exception("Innovation agent failed: %s", exc)
        return None

    artifact_path = save_artifact(
        session_folder=session_folder,
        stage_name="innovation_synthesis",
        artifact_data={
            "selected_modules": selection_metadata,
            "module_payload": module_payload,
            "keywords": step_inputs.keywords,
            "output": innovation_result.get("json"),
            "usage": innovation_result.get("usage"),
        },
    )
    logger.info("✓ innovation_synthesis.json saved at %s", artifact_path)
    return str(artifact_path)


