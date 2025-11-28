from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.core.agents.innovation_synthesis_agent import InnovationSynthesisAgent
from app.core.agents.methodology_extraction_agent import MethodologyExtractionAgent
from app.core.workflows.postprocess_steps import (
    SessionStepInputs,
    load_methodology_items_from_artifact,
    load_step_inputs_from_session,
    run_innovation_synthesis_step,
    run_methodology_extraction_step,
)
from app.services.openai_service import OpenAIService
from app.utils.file_manager import get_session_folder_path
from app.utils.logger import logger


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run workflow Step 5/6 on an existing session (dev tester helper)."
    )
    parser.add_argument(
        "--session-path",
        type=str,
        help="Absolute or relative path to the session folder.",
    )
    parser.add_argument(
        "--session-id",
        type=str,
        help="Session ID (e.g. session_20251127_112630_748edba5). Required if --session-path not provided.",
    )
    parser.add_argument(
        "--username",
        type=str,
        default="dev_tester",
        help="Username folder that contains the session (ignored when --session-path is used).",
    )
    parser.add_argument(
        "--step",
        type=str,
        choices=("methodology", "innovation", "both"),
        default="both",
        help="Which step(s) to run.",
    )
    parser.add_argument(
        "--max-concurrency",
        type=int,
        default=2,
        help="Max concurrent methodology extraction tasks.",
    )
    return parser.parse_args()


def _resolve_session_folder(session_path: Optional[str], session_id: Optional[str], username: Optional[str]) -> Path:
    if session_path:
        folder = Path(session_path).expanduser().resolve()
        if not folder.exists():
            raise FileNotFoundError(f"session_path does not exist: {folder}")
        return folder

    if not session_id:
        raise ValueError("Either --session-path or --session-id must be provided.")

    folder = get_session_folder_path(session_id=session_id, username=username)
    if folder is None or not folder.exists():
        raise FileNotFoundError(f"Unable to locate session folder for {session_id} (username={username})")
    return folder


async def _run(args: argparse.Namespace) -> None:
    session_folder = _resolve_session_folder(args.session_path, args.session_id, args.username)
    logger.info("Using session folder: %s", session_folder)

    step_inputs: SessionStepInputs = load_step_inputs_from_session(session_folder)
    methodology_items: Optional[List[Dict[str, Any]]] = None
    methodology_artifact: Optional[str] = None

    run_methodology = args.step in ("methodology", "both")
    run_innovation = args.step in ("innovation", "both")

    openai_service: Optional[OpenAIService] = None

    if run_methodology:
        openai_service = openai_service or OpenAIService()
        methodology_agent = MethodologyExtractionAgent(openai_service=openai_service)
        methodology_artifact, methodology_items = await run_methodology_extraction_step(
            step_inputs=step_inputs,
            methodology_agent=methodology_agent,
            max_concurrent_tasks=max(1, args.max_concurrency),
        )
        print(f"[Step 5] methodology_extraction_artifact: {methodology_artifact}")
        print(f"[Step 5] methodologies: {len(methodology_items)} entries")
    else:
        methodology_items, existing_artifact = load_methodology_items_from_artifact(session_folder)
        methodology_artifact = str(existing_artifact) if existing_artifact else None
        if not methodology_items:
            raise RuntimeError(
                "No methodology_extraction artifact found. Run with --step methodology first."
            )
        logger.info(
            "Loaded %d methodology entries from existing artifact: %s",
            len(methodology_items),
            methodology_artifact,
        )

    if run_innovation:
        if not methodology_items:
            raise RuntimeError("Innovation step requires ≥3 methodology entries. None available.")

        openai_service = openai_service or OpenAIService()
        innovation_agent = InnovationSynthesisAgent(openai_service=openai_service)
        innovation_artifact = await run_innovation_synthesis_step(
            step_inputs=step_inputs,
            methodology_items=methodology_items,
            innovation_agent=innovation_agent,
        )
        if innovation_artifact:
            print(f"[Step 6] innovation_synthesis_artifact: {innovation_artifact}")
        else:
            print("[Step 6] Innovation synthesis skipped (insufficient eligible inputs).")
    else:
        logger.info("Innovation step skipped per CLI flag.")


def main() -> None:
    args = _parse_args()
    asyncio.run(_run(args))


if __name__ == "__main__":
    main()


