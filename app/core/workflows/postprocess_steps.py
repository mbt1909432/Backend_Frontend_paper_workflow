from __future__ import annotations

import asyncio
import json
import os
import random
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv

from app.core.agents.vision_agent import VisionAgent
from app.core.agents.experiment_extraction_agent import ExperimentExtractionAgent
from app.core.agents.innovation_synthesis_agent import InnovationSynthesisAgent
from app.core.agents.methodology_extraction_agent import MethodologyExtractionAgent
from app.core.agents.writing.methods_writing_agent import MethodsWritingAgent
from app.core.agents.writing.main_results_writing_agent import MainResultsWritingAgent
from app.core.agents.writing.conclusion_writing_agent import ConclusionWritingAgent
from app.core.agents.writing.introduction_writing_agent import IntroductionWritingAgent
from app.core.agents.writing.preliminary_writing_agent import PreliminaryWritingAgent
from app.core.agents.writing.abstract_writing_agent import AbstractWritingAgent
from app.services.anthropic_service import AnthropicService
from app.services.hot_phrase_service import get_recent_hot_phrases
from app.services.openai_service import OpenAIService
from app.utils.file_manager import save_artifact
from app.utils.logger import logger
from app.utils.pdf_converter import pdf_to_pngs
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


async def run_pdf_ocr_step(
    session_folder: Path,
    vision_agent: VisionAgent,
    *,
    max_concurrent_pdfs: int,
    max_concurrent_pages: int,
    max_pages_per_pdf: Optional[int] = None,
) -> Tuple[Dict[str, Any], List[Dict[str, Any]], Path]:
    """
    Execute Step 3 (PDF → PNG → OCR) for a given session folder.

    This step:
    - Reads generated/papers_manifest.json
    - For each paper's PDF, runs pdf_to_pngs + VisionAgent OCR with controlled concurrency
    - Writes artifact/pdf_processing.json
    - Updates papers_manifest.json with OCR paths & status

    Returns:
        (updated_papers_manifest, pdf_processing_results, pdf_processing_artifact_path)
    """
    session_folder = session_folder.resolve()
    generated_dir = session_folder / "generated"
    artifact_dir = session_folder / "artifact"
    manifest_path = generated_dir / "papers_manifest.json"

    if not manifest_path.exists():
        raise FileNotFoundError(f"Missing papers_manifest.json at {manifest_path}")

    papers_manifest: Dict[str, Any] = json.loads(
        manifest_path.read_text(encoding="utf-8")
    )

    logger.info("Step 3: PDF → Text via pdf_to_pngs + VisionAgent (postprocess)")

    processed_root = session_folder / "processed"
    processed_root.mkdir(parents=True, exist_ok=True)

    resolved_page_limit: Optional[int] = max_pages_per_pdf
    if resolved_page_limit is not None and resolved_page_limit <= 0:
        resolved_page_limit = None

    async def process_single_paper(idx: int, paper: Dict[str, Any]) -> Dict[str, Any]:
        paper_id = paper.get("arxiv_id") or f"paper_{idx:02d}"
        paper_status = paper.get("status", "ok")
        result: Dict[str, Any] = {
            "index": idx,
            "arxiv_id": paper_id,
            "pdf_path": paper.get("pdf_path"),
            "status": paper_status,
            "page_count": 0,
            "usage": {
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
            },
            "error": None,
        }

        if paper_status != "ok":
            logger.warning(
                "Skip PDF processing for paper %s (status=%s)",
                paper_id,
                paper_status,
            )
            return result

        pdf_path = paper.get("pdf_path")
        if not pdf_path or not Path(pdf_path).exists():
            logger.error("PDF not found for paper %s: %s", paper_id, pdf_path)
            paper["status"] = "failed"
            result["status"] = "failed"
            result["error"] = f"PDF not found: {pdf_path}"
            return result

        paper_dir = processed_root / f"paper_{idx:02d}"
        images_dir = paper_dir / "images"
        ocr_dir = paper_dir / "ocr"
        logs_dir = paper_dir / "logs"
        images_dir.mkdir(parents=True, exist_ok=True)
        ocr_dir.mkdir(parents=True, exist_ok=True)
        logs_dir.mkdir(parents=True, exist_ok=True)

        logger.info(
            "Start PDF→PNG→OCR for paper #%d (%s) into %s",
            idx,
            paper_id,
            paper_dir,
        )

        try:
            png_paths = pdf_to_pngs(
                pdf_path=str(pdf_path),
                output_dir=str(images_dir),
                dpi=300,
            )
        except Exception as e:  # noqa: BLE001
            logger.exception("pdf_to_pngs failed for %s: %s", paper_id, e)
            paper["status"] = "failed"
            result["status"] = "failed"
            result["error"] = f"pdf_to_pngs failed: {e}"
            return result

        if not png_paths:
            logger.error("No PNG pages generated for %s", paper_id)
            paper["status"] = "failed"
            result["status"] = "failed"
            result["error"] = "No PNG pages generated"
            return result

        logger.info("PDF %s converted to %d PNG pages", paper_id, len(png_paths))

        def _page_sort_key(path: str) -> tuple[int, str]:
            """
            Extract numeric page index if present to keep OCR ordering consistent.
            Falls back to lexical order to avoid crashes on unexpected filenames.
            """
            stem = Path(path).stem
            match = re.search(r"_page_(\d+)", stem)
            if match:
                return (int(match.group(1)), stem)
            return (0, stem)

        sorted_png_paths = sorted(png_paths, key=_page_sort_key)
        if resolved_page_limit is not None:
            limited_paths = sorted_png_paths[:resolved_page_limit]
            if len(limited_paths) < len(sorted_png_paths):
                logger.info(
                    "Limiting OCR for %s to first %d pages (total=%d)",
                    paper_id,
                    len(limited_paths),
                    len(sorted_png_paths),
                )
            sorted_png_paths = limited_paths

        result["page_count"] = len(sorted_png_paths)
        if not sorted_png_paths:
            logger.error("No PNG pages selected for OCR for %s", paper_id)
            paper["status"] = "failed"
            result["status"] = "failed"
            result["error"] = "No PNG pages selected for OCR"
            return result

        # 页面级并发处理
        page_semaphore = asyncio.Semaphore(max_concurrent_pages)

        async def process_single_page(
            page_idx: int, png_path: str
        ) -> tuple[int, str, dict, Optional[str]]:
            """
            处理单页 OCR
            返回: (page_idx, text, usage, error)
            """
            async with page_semaphore:
                try:
                    logger.info(
                        "OCR on paper %s page %d/%d: %s",
                        paper_id,
                        page_idx,
                        len(sorted_png_paths),
                        png_path,
                    )
                    ocr_prompt = (
                        "请直接输出图片中的所有文字内容、图表、表格、公式等，"
                        "不要添加任何描述、说明或解释。保持原有的结构和格式信息。"
                    )
                    ocr_result = await vision_agent.extract_text_from_image(
                        image=png_path,
                        text_prompt=ocr_prompt,
                        temperature=0.3,
                        max_tokens=10000,
                        model=None,
                    )
                    text = ocr_result.get("response") or ""
                    usage = ocr_result.get("usage") or {}

                    logger.info(
                        "OCR completed for paper %s page %d/%d",
                        paper_id,
                        page_idx,
                        len(sorted_png_paths),
                    )

                    return (page_idx, text, usage, None)
                except Exception as e:  # noqa: BLE001
                    logger.exception(
                        "OCR failed on paper %s page %d: %s", paper_id, page_idx, e
                    )
                    return (page_idx, "", {}, f"OCR failed on page {page_idx}: {e}")

        logger.info(
            "Starting concurrent OCR for paper %s: %d pages (max_concurrent=%d)",
            paper_id,
            len(sorted_png_paths),
            max_concurrent_pages,
        )

        page_results = await asyncio.gather(
            *[
                process_single_page(page_idx, png_path)
                for page_idx, png_path in enumerate(sorted_png_paths, start=1)
            ],
            return_exceptions=True,
        )

        # 按页面索引排序并处理结果
        page_texts: List[str] = [""] * len(sorted_png_paths)
        failed_pages: List[tuple[int, str]] = []

        valid_results = []
        for page_result in page_results:
            if isinstance(page_result, Exception):
                logger.error(
                    "Unexpected exception in page processing: %s", page_result
                )
                continue
            valid_results.append(page_result)

        valid_results.sort(key=lambda x: x[0])

        for page_idx, text, usage, error in valid_results:
            if error:
                failed_pages.append((page_idx, error))
                result["status"] = "failed"
                if not result.get("error"):
                    result["error"] = error
            else:
                # 累计 usage
                result["usage"]["input_tokens"] += usage.get("input_tokens", 0)
                result["usage"]["output_tokens"] += usage.get("output_tokens", 0)
                result["usage"]["total_tokens"] += usage.get("total_tokens", 0)

                # 保存到对应位置（page_idx 从 1 开始，数组从 0 开始）
                page_texts[page_idx - 1] = text or ""

                # 保存每页 OCR 结果
                page_txt_path = ocr_dir / f"page_{page_idx}.txt"
                page_txt_path.write_text(text, encoding="utf-8")

        if failed_pages:
            logger.warning(
                "Paper %s: %d pages failed OCR: %s",
                paper_id,
                len(failed_pages),
                [f"page_{idx}" for idx, _ in failed_pages],
            )
            paper["status"] = "failed"
            result["status"] = "failed"
            if not result.get("error"):
                result["error"] = f"Failed pages: {[idx for idx, _ in failed_pages]}"

        # 写 full.txt 与 usage 日志（即使失败也尽量写出已有内容）
        full_txt_path = ocr_dir / "full.txt"
        full_txt_path.write_text("\n\n".join(page_texts), encoding="utf-8")

        usage_log_path = logs_dir / "usage.json"
        usage_log_path.write_text(
            json.dumps(
                {
                    "arxiv_id": paper_id,
                    "index": idx,
                    "status": result["status"],
                    "usage": result["usage"],
                    "page_count": result["page_count"],
                    "error": result["error"],
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        # 在 manifest 中记录 OCR 目录与 full 文本路径
        paper["ocr_dir"] = str(ocr_dir)
        paper["ocr_full_path"] = str(full_txt_path)

        logger.info(
            "Finished OCR for paper #%d (%s): pages=%d, status=%s, ocr_full=%s",
            idx,
            paper_id,
            result["page_count"],
            result["status"],
            full_txt_path,
        )

        return result

    # 控制并发度，对多篇论文做 OCR
    semaphore = asyncio.Semaphore(max_concurrent_pdfs)

    async def sem_task(idx: int, paper: Dict[str, Any]) -> Dict[str, Any]:
        async with semaphore:
            return await process_single_paper(idx, paper)

    pdf_processing_results: List[Dict[str, Any]] = await asyncio.gather(
        *[
            sem_task(idx, paper)
            for idx, paper in enumerate(papers_manifest.get("papers", []), start=1)
        ]
    )

    # 写 pdf_processing.json artifact
    pdf_processing_artifact_path = artifact_dir / "pdf_processing.json"
    pdf_processing_artifact_path.write_text(
        json.dumps(pdf_processing_results, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.info("✓ pdf_processing.json saved at %s", pdf_processing_artifact_path)

    # 重新写回更新后的 papers_manifest（包含 OCR 字段与 status 更新）
    manifest_path.write_text(
        json.dumps(papers_manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.info(
        "✓ papers_manifest.json updated with OCR info at %s",
        manifest_path,
    )

    return papers_manifest, pdf_processing_results, pdf_processing_artifact_path


async def run_markdown_emit_step(
    session_folder: Path,
    papers_manifest: Dict[str, Any],
) -> Tuple[List[Dict[str, Any]], Path, Path]:
    """
    Execute Step 4: emit per-paper Markdown files from OCR full text and
    generate the session-level index markdown.

    This step assumes:
    - Step 2 has produced a populated papers_manifest structure
    - Step 3 has already populated each paper's `ocr_full_path` (when available)

    Returns:
        (markdown_items, markdown_emit_artifact_path, index_md_path)
    """
    session_folder = session_folder.resolve()
    generated_dir = session_folder / "generated"
    artifact_dir = session_folder / "artifact"
    markdown_dir = generated_dir / "markdown"
    markdown_dir.mkdir(parents=True, exist_ok=True)

    markdown_items: List[Dict[str, Any]] = []

    for idx, paper in enumerate(papers_manifest.get("papers", []), start=1):
        if paper.get("status") != "ok":
            continue

        ocr_full_path = paper.get("ocr_full_path")
        if not ocr_full_path or not Path(ocr_full_path).exists():
            logger.warning(
                "Skip markdown for paper %s: missing ocr_full.txt (%s)",
                paper.get("arxiv_id"),
                ocr_full_path,
            )
            paper["status"] = "failed"
            continue

        try:
            ocr_text = Path(ocr_full_path).read_text(encoding="utf-8")
        except Exception as e:  # noqa: BLE001
            logger.exception(
                "Failed to read OCR full text for paper %s: %s",
                paper.get("arxiv_id"),
                e,
            )
            paper["status"] = "failed"
            continue

        # 对 OCR 文本做一次简单清理：压缩多余空行 & 明显噪音行（例如只有 "\" 的行），
        # 避免生成的 Markdown 中出现成片空白。
        cleaned_lines: List[str] = []
        prev_blank = False
        for line in ocr_text.splitlines():
            stripped = line.strip()

            # 将「空行」和某些典型 OCR 噪音行统一视为空行，例如只包含 "\" 的行
            is_blank_or_noise = stripped == "" or stripped == "\\"

            if is_blank_or_noise:
                # 如果上一行已经是空行/噪音，则跳过当前行（保证连续空行最多 1 行）
                if prev_blank:
                    continue
                prev_blank = True
                cleaned_lines.append("")  # 统一用真正的空行占位
            else:
                prev_blank = False
                cleaned_lines.append(line.rstrip())

        cleaned_ocr_text = "\n".join(cleaned_lines).strip()

        title = paper.get("title") or "Untitled"
        arxiv_id = paper.get("arxiv_id") or f"paper_{idx:02d}"
        published = paper.get("published") or ""
        authors = paper.get("authors") or ""
        keyword = paper.get("keyword") or ""
        bibtex_path = paper.get("bibtex_path") or ""

        md_filename = f"paper_{idx:02d}_{arxiv_id}.md"
        md_path = markdown_dir / md_filename

        md_content_lines = [
            f"# {title}",
            "",
            f"- arXiv ID: {arxiv_id}",
            f"- Published: {published}",
            f"- Authors: {authors}",
            f"- Source Keyword: {keyword}",
            f"- DBLP BibTeX: {bibtex_path}",
            "",
            "## Extracted Text",
            "",
            cleaned_ocr_text,
        ]

        md_path.write_text("\n".join(md_content_lines), encoding="utf-8")

        rel_md_path = md_path.relative_to(session_folder)
        markdown_items.append(
            {
                "index": idx,
                "arxiv_id": arxiv_id,
                "title": title,
                "keyword": keyword,
                "markdown_path": str(rel_md_path),
                "status": paper.get("status", "ok"),
            }
        )

        logger.info(
            "Markdown generated for paper #%d (%s): %s",
            idx,
            arxiv_id,
            md_path,
        )

    # 写 markdown_emit.json artifact
    markdown_emit_artifact_path = artifact_dir / "markdown_emit.json"
    markdown_emit_artifact_path.write_text(
        json.dumps(markdown_items, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.info("✓ markdown_emit.json saved at %s", markdown_emit_artifact_path)

    # 生成 summary/index.md（对齐 plan）
    original_query = papers_manifest.get("original_query") or ""
    keywords = papers_manifest.get("rewrite_keywords") or []
    status = papers_manifest.get("status", "ok")
    total_deduped = papers_manifest.get("total_deduped", 0)
    target_paper_count = papers_manifest.get("target_paper_count", 0)

    index_md_path = generated_dir / "index.md"
    index_lines: List[str] = []
    index_lines.append("# Query \u2192 Markdown Summary")
    index_lines.append("")
    index_lines.append(f"**Original Query**: {original_query}")
    index_lines.append("")
    index_lines.append("## Rewrite Keywords")
    index_lines.append("")
    for kw in keywords:
        index_lines.append(f"- {kw}")

    index_lines.append("")
    index_lines.append("## Papers")
    index_lines.append("")
    index_lines.append("| # | Title | arXiv ID | Keyword | Markdown | Status |")
    index_lines.append("|---|-------|----------|---------|----------|--------|")

    for idx, paper in enumerate(papers_manifest.get("papers", []), start=1):
        title = (paper.get("title") or "").replace("|", "\\|")
        arxiv_id = paper.get("arxiv_id") or ""
        keyword = (paper.get("keyword") or "").replace("|", "\\|")
        status_str = paper.get("status", "ok")

        md_item = next(
            (m for m in markdown_items if m["index"] == idx),
            None,
        )
        md_path_str = md_item["markdown_path"] if md_item else ""

        index_lines.append(
            f"| {idx} | {title} | {arxiv_id} | {keyword} | {md_path_str} | {status_str} |"
        )

    if status != "ok":
        index_lines.append("")
        index_lines.append(
            f"> 注意：共找到 {total_deduped} 篇去重论文，少于目标 {target_paper_count} 篇，status = {status}。"
        )

    failed_papers = [
        (i, p)
        for i, p in enumerate(papers_manifest.get("papers", []), start=1)
        if p.get("status") != "ok"
    ]
    if failed_papers:
        index_lines.append("")
        index_lines.append("## Failed or Missing Entries")
        index_lines.append("")
        for idx, p in failed_papers:
            index_lines.append(
                f"- #{idx} {p.get('title') or p.get('arxiv_id')} - status={p.get('status')}"
            )

    index_md_path.write_text("\n".join(index_lines), encoding="utf-8")
    logger.info("✓ index.md saved at %s", index_md_path)

    return markdown_items, markdown_emit_artifact_path, index_md_path


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


async def run_main_results_writing_step(
    step_inputs: SessionStepInputs,
    main_results_agent: MainResultsWritingAgent,
    *,
    temperature: float = 0.6,
    max_tokens: int = 20000,
    model: Optional[str] = None,
) -> List[str]:
    """
    Execute Step 8 (Main Results writing) using experiment artifacts + innovation plans.

    This step aggregates all experiment_extraction entries to build the context,
    then iterates over every innovation_synthesis artifact to craft a Main Results
    package tied to that proposal.
    """

    session_folder = step_inputs.session_folder
    generated_dir = step_inputs.generated_dir
    main_results_dir = generated_dir / "main_results"
    main_results_dir.mkdir(parents=True, exist_ok=True)

    experiment_items, experiment_artifact_path = load_experiment_items_from_artifact(session_folder)
    if not experiment_items:
        logger.warning(
            "Main results writing step skipped: no experiment_extraction artifact found in %s",
            session_folder,
        )
        return []

    def _build_section(item: Dict[str, Any]) -> Optional[str]:
        if item.get("status") != "ok":
            return None
        agent_payload = item.get("agent_payload") or {}
        section_text = (agent_payload.get("experiments") or "").strip()
        if not section_text:
            rel_path = item.get("experiment_path")
            if rel_path:
                experiment_file = session_folder / rel_path
                if experiment_file.exists():
                    try:
                        section_text = experiment_file.read_text(encoding="utf-8").strip()
                    except Exception as exc:
                        logger.warning(
                            "Failed to read experiment markdown %s: %s",
                            experiment_file,
                            exc,
                        )
        if not section_text:
            return None
        header = item.get("title") or item.get("arxiv_id") or f"Experiment #{item.get('index', 0)}"
        return f"{header}\n{section_text}"

    experiment_sections: List[str] = []
    for item in experiment_items:
        section = _build_section(item)
        if section:
            experiment_sections.append(section)

    if not experiment_sections:
        logger.warning(
            "Main results writing step skipped: experiment artifact %s yielded no usable sections",
            experiment_artifact_path,
        )
        return []

    innovation_artifacts = _find_innovation_synthesis_artifacts(session_folder)
    if not innovation_artifacts:
        logger.warning(
            "Main results writing step skipped: no innovation_synthesis*.json artifacts in %s",
            session_folder / "artifact",
        )
        return []

    logger.info(
        "Main results writing: using %d experiment sections across %d innovation artifacts.",
        len(experiment_sections),
        len(innovation_artifacts),
    )

    rel_experiment_artifact = None
    if experiment_artifact_path and experiment_artifact_path.exists():
        rel_experiment_artifact = str(experiment_artifact_path.relative_to(session_folder))

    async def generate_single_main_results(artifact_path: Path, run_index: int) -> Optional[str]:
        try:
            artifact_data = json.loads(artifact_path.read_text(encoding="utf-8"))
            innovation_json = artifact_data.get("output") or {}
            method_proposal = (innovation_json.get("final_method_proposal_text") or "").strip()
            if not method_proposal:
                logger.warning(
                    "Skip main results writing for %s: missing final_method_proposal_text",
                    artifact_path.name,
                )
                return None

            our_method_name = (
                (innovation_json.get("final_proposal_topic") or "").strip()
                or (innovation_json.get("method_context") or {}).get("research_question", "").strip()
                or "Proposed Method"
            )
            our_method = {"full_name": our_method_name}

            logger.info(
                "Main results writing run %d/%d: processing %s",
                run_index + 1,
                len(innovation_artifacts),
                artifact_path.name,
            )

            main_results_result = await main_results_agent.generate_main_results_package(
                experiment_sections=experiment_sections,
                method_proposal=method_proposal,
                our_method=our_method,
                innovation_plan=innovation_json,
                temperature=temperature,
                max_tokens=max_tokens,
                model=model,
            )

            usage_stats = main_results_result.get("usage") or {}
            logger.info(
                "Main results writing run %d/%d finished (prompt_tokens=%s, completion_tokens=%s, total_tokens=%s)",
                run_index + 1,
                len(innovation_artifacts),
                usage_stats.get("prompt_tokens"),
                usage_stats.get("completion_tokens"),
                usage_stats.get("total_tokens"),
            )

            main_results_content = (main_results_result.get("content") or "").strip()
            if not main_results_content:
                logger.warning(
                    "Main results writing run %d/%d: empty content from agent",
                    run_index + 1,
                    len(innovation_artifacts),
                )
                return None

            output_filename = f"{artifact_path.stem}_main_results.tex"
            output_path = main_results_dir / output_filename
            output_path.write_text(main_results_content, encoding="utf-8")
            rel_output_path = output_path.relative_to(session_folder)
            logger.info(
                "Main results LaTeX saved: %s (from %s)",
                output_path,
                artifact_path.name,
            )

            artifact_stem = artifact_path.stem
            if artifact_stem == "innovation_synthesis":
                stage_suffix = ""
            else:
                stage_suffix = artifact_stem.replace("innovation_synthesis", "")

            main_results_artifact_path = save_artifact(
                session_folder=session_folder,
                stage_name=f"main_results_writing{stage_suffix}",
                artifact_data={
                    "run_index": run_index + 1,
                    "source_innovation_artifact": str(artifact_path.relative_to(session_folder)),
                    "source_experiment_artifact": rel_experiment_artifact,
                    "experiment_sections_count": len(experiment_sections),
                    "main_results_path": str(rel_output_path),
                    "main_results_content": main_results_content,
                    "our_method": our_method,
                    "raw_response": main_results_result.get("raw_response"),
                    "usage": usage_stats,
                },
            )

            logger.info(
                "✓ main_results_writing%s.json saved at %s",
                stage_suffix or "",
                main_results_artifact_path,
            )

            return str(main_results_artifact_path)
        except Exception as exc:
            logger.exception(
                "Failed to generate Main Results section for %s: %s",
                artifact_path.name,
                exc,
            )
            return None

    artifact_paths: List[str] = []
    for idx, artifact_path in enumerate(innovation_artifacts):
        result = await generate_single_main_results(artifact_path, idx)
        if result:
            artifact_paths.append(result)

    return artifact_paths


def _find_methods_writing_artifacts(session_folder: Path) -> List[Path]:
    """
    Find all methods_writing*.json artifacts in the session's artifact directory.
    """
    artifact_dir = session_folder / "artifact"
    if not artifact_dir.exists():
        return []
    
    pattern = "methods_writing*.json"
    artifacts = sorted(artifact_dir.glob(pattern))
    return artifacts


def _find_main_results_writing_artifacts(session_folder: Path) -> List[Path]:
    """
    Find all main_results_writing*.json artifacts in the session's artifact directory.
    """
    artifact_dir = session_folder / "artifact"
    if not artifact_dir.exists():
        return []
    
    pattern = "main_results_writing*.json"
    artifacts = sorted(artifact_dir.glob(pattern))
    return artifacts


def _find_introduction_writing_artifacts(session_folder: Path) -> List[Path]:
    """
    Find all introduction_writing*.json artifacts in the session's artifact directory.
    """
    artifact_dir = session_folder / "artifact"
    if not artifact_dir.exists():
        return []
    
    pattern = "introduction_writing*.json"
    artifacts = sorted(artifact_dir.glob(pattern))
    return artifacts


def _find_conclusion_writing_artifacts(session_folder: Path) -> List[Path]:
    """
    Find all conclusion_writing*.json artifacts in the session's artifact directory.
    """
    artifact_dir = session_folder / "artifact"
    if not artifact_dir.exists():
        return []
    
    pattern = "conclusion_writing*.json"
    artifacts = sorted(artifact_dir.glob(pattern))
    return artifacts


def _extract_stage_suffix(artifact_stem: str, prefix: str) -> str:
    """
    Extract stage suffix from artifact stem.
    Example: 'methods_writing_2' -> '_2', 'main_results_writing' -> ''
    """
    if artifact_stem == prefix:
        return ""
    suffix = artifact_stem.replace(prefix, "")
    return suffix if suffix else ""


async def run_conclusion_writing_step(
    step_inputs: SessionStepInputs,
    conclusion_agent: ConclusionWritingAgent,
    *,
    temperature: float = 0.7,
    max_tokens: int = 6000,
    model: Optional[str] = None,
) -> List[str]:
    """
    Execute Step 9 (Conclusion writing) using methods_writing and main_results_writing artifacts.
    
    This step reads all methods_writing*.json and main_results_writing*.json artifacts,
    matches them by suffix (e.g., innovation_synthesis -> methods_writing -> main_results_writing),
    and generates Conclusion sections for each matching pair.
    
    Args:
        step_inputs: Session inputs containing session folder and paths
        conclusion_agent: Initialized ConclusionWritingAgent instance
        temperature: Generation temperature (default: 0.7)
        max_tokens: Maximum tokens for generation (default: 6000)
        model: Model name (optional, uses service default)
    
    Returns:
        List of artifact paths for the generated conclusion_writing*.json files
    """
    session_folder = step_inputs.session_folder
    generated_dir = step_inputs.generated_dir
    conclusion_dir = generated_dir / "conclusion"
    conclusion_dir.mkdir(parents=True, exist_ok=True)
    
    # Find all artifacts
    methods_artifacts = _find_methods_writing_artifacts(session_folder)
    main_results_artifacts = _find_main_results_writing_artifacts(session_folder)
    innovation_artifacts = _find_innovation_synthesis_artifacts(session_folder)
    
    if not methods_artifacts:
        logger.warning(
            "Conclusion writing step skipped: no methods_writing*.json artifacts found in %s",
            session_folder / "artifact",
        )
        return []
    
    if not main_results_artifacts:
        logger.warning(
            "Conclusion writing step skipped: no main_results_writing*.json artifacts found in %s",
            session_folder / "artifact",
        )
        return []
    
    logger.info(
        "Found %d methods_writing, %d main_results_writing, %d innovation_synthesis artifacts",
        len(methods_artifacts),
        len(main_results_artifacts),
        len(innovation_artifacts),
    )
    
    # Build a mapping from suffix to artifacts
    def _get_suffix_mapping(artifacts: List[Path], prefix: str) -> Dict[str, Path]:
        mapping: Dict[str, Path] = {}
        for artifact in artifacts:
            suffix = _extract_stage_suffix(artifact.stem, prefix)
            mapping[suffix] = artifact
        return mapping
    
    methods_mapping = _get_suffix_mapping(methods_artifacts, "methods_writing")
    main_results_mapping = _get_suffix_mapping(main_results_artifacts, "main_results_writing")
    innovation_mapping = _get_suffix_mapping(innovation_artifacts, "innovation_synthesis")
    
    # Find all matching suffixes
    matching_suffixes = set(methods_mapping.keys()) & set(main_results_mapping.keys())
    
    if not matching_suffixes:
        logger.warning(
            "Conclusion writing step skipped: no matching suffixes between methods_writing and main_results_writing artifacts"
        )
        return []
    
    logger.info(
        "Found %d matching artifact pairs, generating Conclusion sections...",
        len(matching_suffixes),
    )
    
    async def generate_single_conclusion(suffix: str, run_index: int) -> Optional[str]:
        """Generate Conclusion section for a single matching artifact pair."""
        try:
            methods_artifact_path = methods_mapping[suffix]
            main_results_artifact_path = main_results_mapping[suffix]
            
            # Load methods artifact
            methods_artifact_data = json.loads(methods_artifact_path.read_text(encoding="utf-8"))
            methods_latex_path_str = methods_artifact_data.get("latex_path")
            if not methods_latex_path_str:
                logger.warning(
                    "Skip conclusion writing for suffix '%s': missing latex_path in methods artifact",
                    suffix or "''",
                )
                return None
            
            methods_latex_path = session_folder / methods_latex_path_str
            if not methods_latex_path.exists():
                logger.warning(
                    "Skip conclusion writing for suffix '%s': methods LaTeX file not found: %s",
                    suffix or "''",
                    methods_latex_path,
                )
                return None
            
            # Load main results artifact
            main_results_artifact_data = json.loads(main_results_artifact_path.read_text(encoding="utf-8"))
            main_results_latex_path_str = main_results_artifact_data.get("main_results_path")
            if not main_results_latex_path_str:
                logger.warning(
                    "Skip conclusion writing for suffix '%s': missing main_results_path in main_results artifact",
                    suffix or "''",
                )
                return None
            
            main_results_latex_path = session_folder / main_results_latex_path_str
            if not main_results_latex_path.exists():
                logger.warning(
                    "Skip conclusion writing for suffix '%s': main_results LaTeX file not found: %s",
                    suffix or "''",
                    main_results_latex_path,
                )
                return None
            
            # Load innovation JSON if available
            innovation_json: Optional[Dict[str, Any]] = None
            if suffix in innovation_mapping:
                innovation_artifact_path = innovation_mapping[suffix]
                try:
                    innovation_artifact_data = json.loads(innovation_artifact_path.read_text(encoding="utf-8"))
                    innovation_json = innovation_artifact_data.get("output")
                except Exception as exc:
                    logger.warning(
                        "Failed to load innovation JSON for suffix '%s': %s (will proceed without it)",
                        suffix or "''",
                        exc,
                    )
            
            # Read LaTeX contents
            try:
                methods_latex_content = methods_latex_path.read_text(encoding="utf-8").strip()
                main_results_latex_content = main_results_latex_path.read_text(encoding="utf-8").strip()
            except Exception as exc:
                logger.exception(
                    "Failed to read LaTeX files for suffix '%s': %s",
                    suffix or "''",
                    exc,
                )
                return None
            
            if not methods_latex_content or not main_results_latex_content:
                logger.warning(
                    "Skip conclusion writing for suffix '%s': empty LaTeX content",
                    suffix or "''",
                )
                return None
            
            logger.info(
                "Conclusion writing run %d/%d: processing suffix '%s' (methods=%s, main_results=%s)",
                run_index + 1,
                len(matching_suffixes),
                suffix or "''",
                methods_artifact_path.name,
                main_results_artifact_path.name,
            )
            
            # Generate Conclusion section
            conclusion_result = await conclusion_agent.generate_conclusion_section(
                methods_latex_content=methods_latex_content,
                experiment_latex_content=main_results_latex_content,
                innovation_json=innovation_json,
                temperature=temperature,
                max_tokens=max_tokens,
                model=model,
            )
            
            usage_stats = conclusion_result.get("usage") or {}
            logger.info(
                "Conclusion writing run %d/%d finished (prompt_tokens=%s, completion_tokens=%s, total_tokens=%s)",
                run_index + 1,
                len(matching_suffixes),
                usage_stats.get("prompt_tokens"),
                usage_stats.get("completion_tokens"),
                usage_stats.get("total_tokens"),
            )
            
            conclusion_content = conclusion_result.get("content", "").strip()
            if not conclusion_content:
                logger.warning(
                    "Conclusion writing run %d/%d: empty content from agent",
                    run_index + 1,
                    len(matching_suffixes),
                )
                return None
            
            # Save LaTeX content to file
            latex_filename = f"innovation_synthesis{suffix}_conclusion.tex"
            latex_path = conclusion_dir / latex_filename
            latex_path.write_text(conclusion_content, encoding="utf-8")
            rel_latex_path = latex_path.relative_to(session_folder)
            logger.info(
                "Conclusion LaTeX saved: %s (suffix='%s')",
                latex_path,
                suffix or "''",
            )
            
            # Save artifact
            conclusion_artifact_path = save_artifact(
                session_folder=session_folder,
                stage_name=f"conclusion_writing{suffix}",
                artifact_data={
                    "run_index": run_index + 1,
                    "source_methods_artifact": str(methods_artifact_path.relative_to(session_folder)),
                    "source_main_results_artifact": str(main_results_artifact_path.relative_to(session_folder)),
                    "source_innovation_artifact": (
                        str(innovation_mapping[suffix].relative_to(session_folder))
                        if suffix in innovation_mapping
                        else None
                    ),
                    "latex_path": str(rel_latex_path),
                    "latex_content": conclusion_content,
                    "raw_response": conclusion_result.get("raw_response"),
                    "usage": usage_stats,
                },
            )
            
            logger.info(
                "✓ conclusion_writing%s.json saved at %s",
                suffix or "",
                conclusion_artifact_path,
            )
            
            return str(conclusion_artifact_path)
            
        except Exception as exc:
            logger.exception(
                "Failed to generate Conclusion section for suffix '%s': %s",
                suffix or "''",
                exc,
            )
            return None
    
    # Process all matching pairs sequentially
    artifact_paths: List[str] = []
    sorted_suffixes = sorted(matching_suffixes)
    for idx, suffix in enumerate(sorted_suffixes):
        result = await generate_single_conclusion(suffix, idx)
        if result:
            artifact_paths.append(result)
    
    return artifact_paths


async def run_introduction_writing_step(
    step_inputs: SessionStepInputs,
    introduction_agent: IntroductionWritingAgent,
    *,
    temperature: float = 0.7,
    max_tokens: int = 8000,
    model: Optional[str] = None,
) -> List[str]:
    """
    Execute Step 9 (Introduction writing) using methods_writing artifacts and methodology_items.
    
    This step reads all methods_writing*.json artifacts, matches them with innovation_synthesis artifacts,
    and generates Introduction sections for each matching pair.
    
    It uses methodology_items to build retrieved_papers (combining problem_statement + methodology).
    
    Args:
        step_inputs: Session inputs containing session folder and paths
        introduction_agent: Initialized IntroductionWritingAgent instance
        temperature: Generation temperature (default: 0.7)
        max_tokens: Maximum tokens for generation (default: 8000)
        model: Model name (optional, uses service default)
    
    Returns:
        List of artifact paths for the generated introduction_writing*.json files
    """
    session_folder = step_inputs.session_folder
    generated_dir = step_inputs.generated_dir
    introduction_dir = generated_dir / "introduction"
    introduction_dir.mkdir(parents=True, exist_ok=True)
    
    # Find all artifacts
    methods_artifacts = _find_methods_writing_artifacts(session_folder)
    innovation_artifacts = _find_innovation_synthesis_artifacts(session_folder)
    
    # Load methodology_items to build retrieved_papers
    methodology_items, _ = load_methodology_items_from_artifact(session_folder)
    
    if not methods_artifacts:
        logger.warning(
            "Introduction writing step skipped: no methods_writing*.json artifacts found in %s",
            session_folder / "artifact",
        )
        return []
    
    # Build retrieved_papers from methodology_items
    def _build_retrieved_papers() -> List[str]:
        """Build retrieved_papers list from methodology_items."""
        retrieved_papers: List[str] = []
        for item in methodology_items:
            if item.get("status") != "ok":
                continue
            
            problem_statement_path = item.get("problem_statement_path")
            methodology_path = item.get("methodology_path")
            
            if not problem_statement_path and not methodology_path:
                continue
            
            paper_sections: List[str] = []
            
            # Read problem statement if available
            if problem_statement_path:
                problem_file = session_folder / problem_statement_path
                if problem_file.exists():
                    try:
                        problem_text = problem_file.read_text(encoding="utf-8").strip()
                        if problem_text:
                            paper_sections.append(problem_text)
                    except Exception as exc:
                        logger.warning(
                            "Failed to read problem statement from %s: %s",
                            problem_file,
                            exc,
                        )
            
            # Read methodology if available
            if methodology_path:
                methodology_file = session_folder / methodology_path
                if methodology_file.exists():
                    try:
                        methodology_text = methodology_file.read_text(encoding="utf-8").strip()
                        if methodology_text:
                            paper_sections.append(methodology_text)
                    except Exception as exc:
                        logger.warning(
                            "Failed to read methodology from %s: %s",
                            methodology_file,
                            exc,
                        )
            
            # Combine problem statement + methodology
            if paper_sections:
                combined_text = "\n\n".join(paper_sections)
                retrieved_papers.append(combined_text)
        
        return retrieved_papers
    
    retrieved_papers = _build_retrieved_papers()
    
    if not retrieved_papers:
        logger.warning(
            "Introduction writing step skipped: no valid methodology items found to build retrieved_papers"
        )
        return []
    
    logger.info(
        "Found %d methods_writing, %d innovation_synthesis artifacts, %d retrieved papers",
        len(methods_artifacts),
        len(innovation_artifacts),
        len(retrieved_papers),
    )
    
    # Build a mapping from suffix to artifacts
    def _get_suffix_mapping(artifacts: List[Path], prefix: str) -> Dict[str, Path]:
        mapping: Dict[str, Path] = {}
        for artifact in artifacts:
            suffix = _extract_stage_suffix(artifact.stem, prefix)
            mapping[suffix] = artifact
        return mapping
    
    methods_mapping = _get_suffix_mapping(methods_artifacts, "methods_writing")
    innovation_mapping = _get_suffix_mapping(innovation_artifacts, "innovation_synthesis")
    
    # Find all matching suffixes (methods_writing must have corresponding innovation_synthesis)
    matching_suffixes = set(methods_mapping.keys()) & set(innovation_mapping.keys())
    
    if not matching_suffixes:
        logger.warning(
            "Introduction writing step skipped: no matching suffixes between methods_writing and innovation_synthesis artifacts"
        )
        return []
    
    logger.info(
        "Found %d matching artifact pairs, generating Introduction sections...",
        len(matching_suffixes),
    )
    
    async def generate_single_introduction(suffix: str, run_index: int) -> Optional[str]:
        """Generate Introduction section for a single matching artifact pair."""
        try:
            methods_artifact_path = methods_mapping[suffix]
            innovation_artifact_path = innovation_mapping[suffix]
            
            # Load methods artifact
            methods_artifact_data = json.loads(methods_artifact_path.read_text(encoding="utf-8"))
            methods_latex_path_str = methods_artifact_data.get("latex_path")
            if not methods_latex_path_str:
                logger.warning(
                    "Skip introduction writing for suffix '%s': missing latex_path in methods artifact",
                    suffix or "''",
                )
                return None
            
            methods_latex_path = session_folder / methods_latex_path_str
            if not methods_latex_path.exists():
                logger.warning(
                    "Skip introduction writing for suffix '%s': methods LaTeX file not found: %s",
                    suffix or "''",
                    methods_latex_path,
                )
                return None
            
            # Load innovation JSON
            try:
                innovation_artifact_data = json.loads(innovation_artifact_path.read_text(encoding="utf-8"))
                innovation_json = innovation_artifact_data.get("output")
            except Exception as exc:
                logger.warning(
                    "Failed to load innovation JSON for suffix '%s': %s",
                    suffix or "''",
                    exc,
                )
                innovation_json = None
            
            # Read Methods LaTeX content
            try:
                methods_latex_content = methods_latex_path.read_text(encoding="utf-8").strip()
            except Exception as exc:
                logger.exception(
                    "Failed to read Methods LaTeX file for suffix '%s': %s",
                    suffix or "''",
                    exc,
                )
                return None
            
            if not methods_latex_content:
                logger.warning(
                    "Skip introduction writing for suffix '%s': empty Methods LaTeX content",
                    suffix or "''",
                )
                return None
            
            logger.info(
                "Introduction writing run %d/%d: processing suffix '%s' (methods=%s, innovation=%s)",
                run_index + 1,
                len(matching_suffixes),
                suffix or "''",
                methods_artifact_path.name,
                innovation_artifact_path.name,
            )
            
            # Generate Introduction section
            introduction_result = await introduction_agent.generate_introduction_section(
                retrieved_papers=retrieved_papers,
                methods_latex_content=methods_latex_content,
                innovation_json=innovation_json,
                temperature=temperature,
                max_tokens=max_tokens,
                model=model,
            )
            
            usage_stats = introduction_result.get("usage") or {}
            logger.info(
                "Introduction writing run %d/%d finished (prompt_tokens=%s, completion_tokens=%s, total_tokens=%s)",
                run_index + 1,
                len(matching_suffixes),
                usage_stats.get("prompt_tokens"),
                usage_stats.get("completion_tokens"),
                usage_stats.get("total_tokens"),
            )
            
            introduction_content = introduction_result.get("content", "").strip()
            if not introduction_content:
                logger.warning(
                    "Introduction writing run %d/%d: empty content from agent",
                    run_index + 1,
                    len(matching_suffixes),
                )
                return None
            
            # Save LaTeX content to file
            latex_filename = f"innovation_synthesis{suffix}_introduction.tex"
            latex_path = introduction_dir / latex_filename
            latex_path.write_text(introduction_content, encoding="utf-8")
            rel_latex_path = latex_path.relative_to(session_folder)
            logger.info(
                "Introduction LaTeX saved: %s (suffix='%s')",
                latex_path,
                suffix or "''",
            )
            
            # Save artifact
            introduction_artifact_path = save_artifact(
                session_folder=session_folder,
                stage_name=f"introduction_writing{suffix}",
                artifact_data={
                    "run_index": run_index + 1,
                    "source_methods_artifact": str(methods_artifact_path.relative_to(session_folder)),
                    "source_innovation_artifact": str(innovation_artifact_path.relative_to(session_folder)),
                    "retrieved_papers_count": len(retrieved_papers),
                    "latex_path": str(rel_latex_path),
                    "latex_content": introduction_content,
                    "raw_response": introduction_result.get("raw_response"),
                    "usage": usage_stats,
                },
            )
            
            logger.info(
                "✓ introduction_writing%s.json saved at %s",
                suffix or "",
                introduction_artifact_path,
            )
            
            return str(introduction_artifact_path)
            
        except Exception as exc:
            logger.exception(
                "Failed to generate Introduction section for suffix '%s': %s",
                suffix or "''",
                exc,
            )
            return None
    
    # Process all matching pairs sequentially
    artifact_paths: List[str] = []
    sorted_suffixes = sorted(matching_suffixes)
    for idx, suffix in enumerate(sorted_suffixes):
        result = await generate_single_introduction(suffix, idx)
        if result:
            artifact_paths.append(result)
    
    return artifact_paths


async def run_preliminary_writing_step(
    step_inputs: SessionStepInputs,
    preliminary_agent: PreliminaryWritingAgent,
    *,
    temperature: float = 0.7,
    max_tokens: int = 2000,
    model: Optional[str] = None,
) -> List[str]:
    """
    Execute Step 9 (Preliminary writing) using methods_writing artifacts and innovation_synthesis artifacts.
    
    This step reads all methods_writing*.json artifacts, matches them with innovation_synthesis artifacts,
    and generates Preliminary sections for each matching pair.
    
    Args:
        step_inputs: Session inputs containing session folder and paths
        preliminary_agent: Initialized PreliminaryWritingAgent instance
        temperature: Generation temperature (default: 0.7)
        max_tokens: Maximum tokens for generation (default: 2000)
        model: Model name (optional, uses service default)
    
    Returns:
        List of artifact paths for the generated preliminary_writing*.json files
    """
    session_folder = step_inputs.session_folder
    generated_dir = step_inputs.generated_dir
    preliminary_dir = generated_dir / "preliminary"
    preliminary_dir.mkdir(parents=True, exist_ok=True)
    
    # Find all artifacts
    methods_artifacts = _find_methods_writing_artifacts(session_folder)
    innovation_artifacts = _find_innovation_synthesis_artifacts(session_folder)
    
    if not methods_artifacts:
        logger.warning(
            "Preliminary writing step skipped: no methods_writing*.json artifacts found in %s",
            session_folder / "artifact",
        )
        return []
    
    if not innovation_artifacts:
        logger.warning(
            "Preliminary writing step skipped: no innovation_synthesis*.json artifacts found in %s",
            session_folder / "artifact",
        )
        return []
    
    logger.info(
        "Found %d methods_writing, %d innovation_synthesis artifacts",
        len(methods_artifacts),
        len(innovation_artifacts),
    )
    
    # Build a mapping from suffix to artifacts
    def _get_suffix_mapping(artifacts: List[Path], prefix: str) -> Dict[str, Path]:
        mapping: Dict[str, Path] = {}
        for artifact in artifacts:
            suffix = _extract_stage_suffix(artifact.stem, prefix)
            mapping[suffix] = artifact
        return mapping
    
    methods_mapping = _get_suffix_mapping(methods_artifacts, "methods_writing")
    innovation_mapping = _get_suffix_mapping(innovation_artifacts, "innovation_synthesis")
    
    # Find all matching suffixes (methods_writing must have corresponding innovation_synthesis)
    matching_suffixes = set(methods_mapping.keys()) & set(innovation_mapping.keys())
    
    if not matching_suffixes:
        logger.warning(
            "Preliminary writing step skipped: no matching suffixes between methods_writing and innovation_synthesis artifacts"
        )
        return []
    
    logger.info(
        "Found %d matching artifact pairs, generating Preliminary sections...",
        len(matching_suffixes),
    )
    
    async def generate_single_preliminary(suffix: str, run_index: int) -> Optional[str]:
        """Generate Preliminary section for a single matching artifact pair."""
        try:
            methods_artifact_path = methods_mapping[suffix]
            innovation_artifact_path = innovation_mapping[suffix]
            
            # Load methods artifact
            methods_artifact_data = json.loads(methods_artifact_path.read_text(encoding="utf-8"))
            methods_latex_path_str = methods_artifact_data.get("latex_path")
            if not methods_latex_path_str:
                logger.warning(
                    "Skip preliminary writing for suffix '%s': missing latex_path in methods artifact",
                    suffix or "''",
                )
                return None
            
            methods_latex_path = session_folder / methods_latex_path_str
            if not methods_latex_path.exists():
                logger.warning(
                    "Skip preliminary writing for suffix '%s': methods LaTeX file not found: %s",
                    suffix or "''",
                    methods_latex_path,
                )
                return None
            
            # Load innovation JSON
            try:
                innovation_artifact_data = json.loads(innovation_artifact_path.read_text(encoding="utf-8"))
                innovation_json = innovation_artifact_data.get("output")
            except Exception as exc:
                logger.warning(
                    "Failed to load innovation JSON for suffix '%s': %s",
                    suffix or "''",
                    exc,
                )
                innovation_json = None
            
            # Read Methods LaTeX content
            try:
                methods_latex_content = methods_latex_path.read_text(encoding="utf-8").strip()
            except Exception as exc:
                logger.exception(
                    "Failed to read Methods LaTeX file for suffix '%s': %s",
                    suffix or "''",
                    exc,
                )
                return None
            
            if not methods_latex_content:
                logger.warning(
                    "Skip preliminary writing for suffix '%s': empty Methods LaTeX content",
                    suffix or "''",
                )
                return None
            
            logger.info(
                "Preliminary writing run %d/%d: processing suffix '%s' (methods=%s, innovation=%s)",
                run_index + 1,
                len(matching_suffixes),
                suffix or "''",
                methods_artifact_path.name,
                innovation_artifact_path.name,
            )
            
            # Generate Preliminary section
            preliminary_result = await preliminary_agent.generate_preliminary_section(
                innovation_json=innovation_json,
                methods_latex_content=methods_latex_content,
                temperature=temperature,
                max_tokens=max_tokens,
                model=model,
            )
            
            usage_stats = preliminary_result.get("usage") or {}
            logger.info(
                "Preliminary writing run %d/%d finished (prompt_tokens=%s, completion_tokens=%s, total_tokens=%s)",
                run_index + 1,
                len(matching_suffixes),
                usage_stats.get("prompt_tokens"),
                usage_stats.get("completion_tokens"),
                usage_stats.get("total_tokens"),
            )
            
            preliminary_content = preliminary_result.get("content", "").strip()
            if not preliminary_content:
                logger.warning(
                    "Preliminary writing run %d/%d: empty content from agent",
                    run_index + 1,
                    len(matching_suffixes),
                )
                return None
            
            # Save LaTeX content to file
            latex_filename = f"innovation_synthesis{suffix}_preliminary.tex"
            latex_path = preliminary_dir / latex_filename
            latex_path.write_text(preliminary_content, encoding="utf-8")
            rel_latex_path = latex_path.relative_to(session_folder)
            logger.info(
                "Preliminary LaTeX saved: %s (suffix='%s')",
                latex_path,
                suffix or "''",
            )
            
            # Save artifact
            preliminary_artifact_path = save_artifact(
                session_folder=session_folder,
                stage_name=f"preliminary_writing{suffix}",
                artifact_data={
                    "run_index": run_index + 1,
                    "source_methods_artifact": str(methods_artifact_path.relative_to(session_folder)),
                    "source_innovation_artifact": str(innovation_artifact_path.relative_to(session_folder)),
                    "latex_path": str(rel_latex_path),
                    "latex_content": preliminary_content,
                    "raw_response": preliminary_result.get("raw_response"),
                    "usage": usage_stats,
                },
            )
            
            logger.info(
                "✓ preliminary_writing%s.json saved at %s",
                suffix or "",
                preliminary_artifact_path,
            )
            
            return str(preliminary_artifact_path)
            
        except Exception as exc:
            logger.exception(
                "Failed to generate Preliminary section for suffix '%s': %s",
                suffix or "''",
                exc,
            )
            return None
    
    # Process all matching pairs sequentially
    artifact_paths: List[str] = []
    sorted_suffixes = sorted(matching_suffixes)
    for idx, suffix in enumerate(sorted_suffixes):
        result = await generate_single_preliminary(suffix, idx)
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


async def step_3_step4(
    max_concurrent_pdfs: int = 3,
    max_concurrent_pages: int = 8,
    max_pages_per_pdf: Optional[int] = None,
) -> None:
    """
    测试入口：复用已有 papers_manifest.json，依次运行
    Step 3（PDF → PNG → OCR）和 Step 4（Markdown 生成）。
    """

    # TODO: 修改为真实 session 路径，例如 Path("E:/.../session_20251128_xxx")
    test_session_folder = Path(
        r"E:\pycharm_project\software_idea\academic draft agentic_workflow\app\core\workflows\output\2025_12_4\session_20251204_173727_a37e084c"
    ).resolve()

    _load_local_env_file()

    anthropic_service = AnthropicService()
    vision_agent = VisionAgent(anthropic_service=anthropic_service)

    papers_manifest, pdf_results, pdf_artifact = await run_pdf_ocr_step(
        session_folder=test_session_folder,
        vision_agent=vision_agent,
        max_concurrent_pdfs=max_concurrent_pdfs,
        max_concurrent_pages=max_concurrent_pages,
        max_pages_per_pdf=max_pages_per_pdf,
    )

    logger.info("Step 3 finished for session: %s", test_session_folder)
    logger.info(
        "Updated papers_manifest has %d entries",
        len(papers_manifest.get("papers", [])),
    )
    logger.info(
        "pdf_processing.json saved at %s (entries=%d)",
        pdf_artifact,
        len(pdf_results),
    )

    # 继续运行 Step 4：根据 OCR 文本生成 Markdown
    logger.info("Running Step 4: Emit Markdown files from OCR text")
    markdown_items, markdown_emit_artifact_path, index_md_path = (
        await run_markdown_emit_step(
            session_folder=test_session_folder,
            papers_manifest=papers_manifest,
        )
    )

    logger.info(
        "Step 4 finished. Generated %d markdown items. Artifact: %s, index.md: %s",
        len(markdown_items),
        markdown_emit_artifact_path,
        index_md_path,
    )


async def main_run_step_6_only(
    custom_keywords: Optional[List[str]] = None,
    innovation_run_count: int = 1,
) -> None:
    """
    测试入口：复用已有 methodology_extraction.json，仅运行 Step 6（Innovation）。
    """

    # TODO: 修改为真实 session 路径，例如 Path("E:/.../session_20251128_xxx")
    test_session_folder = Path(r"E:\pycharm_project\software_idea\academic draft agentic_workflow\app\core\workflows\output\2025_12_4\session_20251204_173727_a37e084c").resolve()

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
    test_session_folder = Path(r"E:\pycharm_project\software_idea\academic draft agentic_workflow\app\core\workflows\output\2025_12_5\session_20251205_175558_006f8492").resolve()

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


async def main_run_step_8_only(
    temperature: float = 0.6,
    max_tokens: int = 9000,
    model: Optional[str] = None,
) -> None:
    """
    测试入口：复用已有 experiment_extraction.json + innovation_synthesis*.json，仅运行 Step 8（Main Results Writing）。
    """

    # TODO: 修改为真实 session 路径，例如 Path("E:/.../session_20251128_xxx")
    test_session_folder = Path(r"E:\pycharm_project\software_idea\academic draft agentic_workflow\app\core\workflows\output\2025_12_5\session_20251205_175558_006f8492").resolve()

    _load_local_env_file()

    step_inputs = load_step_inputs_from_session(test_session_folder)

    openai_service = OpenAIService()
    main_results_agent = MainResultsWritingAgent(openai_service=openai_service)

    main_results_artifacts = await run_main_results_writing_step(
        step_inputs=step_inputs,
        main_results_agent=main_results_agent,
        temperature=temperature,
        max_tokens=max_tokens,
        model=model,
    )

    if main_results_artifacts:
        logger.info("Main results writing artifacts: %s", main_results_artifacts)
    else:
        logger.info("Main results writing skipped or failed.")


async def main_run_step_9_only(
    introduction_temperature: float = 0.7,
    introduction_max_tokens: int = 8000,
    conclusion_temperature: float = 0.7,
    conclusion_max_tokens: int = 6000,
    preliminary_temperature: float = 0.7,
    preliminary_max_tokens: int = 2000,
    model: Optional[str] = None,
) -> None:
    """
    测试入口：复用已有 methods_writing*.json + main_results_writing*.json，运行 Step 9（Introduction + Conclusion + Preliminary Writing）。
    """

    # TODO: 修改为真实 session 路径，例如 Path("E:/.../session_20251128_xxx")
    test_session_folder = Path(r"E:\pycharm_project\software_idea\academic draft agentic_workflow\app\core\workflows\output\2025_12_5\session_20251205_175558_006f8492").resolve()

    _load_local_env_file()

    step_inputs = load_step_inputs_from_session(test_session_folder)

    openai_service = OpenAIService()
    introduction_agent = IntroductionWritingAgent(openai_service=openai_service)
    conclusion_agent = ConclusionWritingAgent(openai_service=openai_service)
    preliminary_agent = PreliminaryWritingAgent(openai_service=openai_service)

    # Run Introduction, Conclusion, and Preliminary writing in parallel
    introduction_artifacts, conclusion_artifacts, preliminary_artifacts = await asyncio.gather(
        run_introduction_writing_step(
            step_inputs=step_inputs,
            introduction_agent=introduction_agent,
            temperature=introduction_temperature,
            max_tokens=introduction_max_tokens,
            model=model,
        ),
        run_conclusion_writing_step(
            step_inputs=step_inputs,
            conclusion_agent=conclusion_agent,
            temperature=conclusion_temperature,
            max_tokens=conclusion_max_tokens,
            model=model,
        ),
        run_preliminary_writing_step(
            step_inputs=step_inputs,
            preliminary_agent=preliminary_agent,
            temperature=preliminary_temperature,
            max_tokens=preliminary_max_tokens,
            model=model,
        ),
    )

    if introduction_artifacts:
        logger.info("Introduction writing artifacts: %s", introduction_artifacts)
    else:
        logger.info("Introduction writing skipped or failed.")

    if conclusion_artifacts:
        logger.info("Conclusion writing artifacts: %s", conclusion_artifacts)
    else:
        logger.info("Conclusion writing skipped or failed.")

    if preliminary_artifacts:
        logger.info("Preliminary writing artifacts: %s", preliminary_artifacts)
    else:
        logger.info("Preliminary writing skipped or failed.")


async def main_run_steps_5_to_8(
    session_folder: Path,
    *,
    custom_keywords: Optional[List[str]] = None,
    innovation_run_count: int = 1,
    methods_temperature: float = 0.7,
    methods_max_tokens: int = 20000,
    main_results_temperature: float = 0.6,
    main_results_max_tokens: int = 40000,
    main_results_model: Optional[str] = None,
) -> None:
    """
    统一封装：在给定 session_folder 上按顺序运行 Step 5~8。

    - Step 5: Methodology & Experiment 提取
    - Step 6: Innovation synthesis
    - Step 7: Methods writing
    - Step 8: Main Results writing
    """
    session_folder = session_folder.resolve()

    _load_local_env_file()
    step_inputs = load_step_inputs_from_session(session_folder)

    openai_service = OpenAIService()
    methodology_agent = MethodologyExtractionAgent(openai_service=openai_service)
    experiment_agent = ExperimentExtractionAgent(openai_service=openai_service)
    innovation_agent = InnovationSynthesisAgent(openai_service=openai_service)
    methods_writing_agent = MethodsWritingAgent(openai_service=openai_service)
    main_results_agent = MainResultsWritingAgent(openai_service=openai_service)

    # Step 5: 并行跑 Methodology + Experiment 提取
    (methodology_artifact, methodology_items), (experiment_artifact, experiment_items) = await asyncio.gather(
        run_methodology_extraction_step(
            step_inputs=step_inputs,
            methodology_agent=methodology_agent,
            max_concurrent_tasks=2,
        ),
        run_experiment_extraction_step(
            step_inputs=step_inputs,
            experiment_agent=experiment_agent,
            max_concurrent_tasks=2,
        ),
    )

    logger.info("Methodology artifact: %s", methodology_artifact)
    logger.info("Experiment artifact: %s", experiment_artifact)

    if not methodology_items:
        logger.info("No methodology items extracted; skip Steps 6–8.")
        return

    # Step 6: Innovation synthesis（可能生成多个 run）
    innovation_artifacts = await run_innovation_synthesis_step(
        step_inputs=step_inputs,
        methodology_items=methodology_items,
        innovation_agent=innovation_agent,
        override_keywords=custom_keywords,
        run_count=innovation_run_count,
    )

    if not innovation_artifacts:
        logger.info("Innovation synthesis skipped or failed; skip Steps 7–8.")
        return

    logger.info("Innovation artifacts: %s", innovation_artifacts)

    # Step 7: Methods writing（基于所有 innovation_synthesis*.json）
    methods_artifacts = await run_methods_writing_step(
        step_inputs=step_inputs,
        methods_writing_agent=methods_writing_agent,
        temperature=methods_temperature,
        max_tokens=methods_max_tokens,
    )
    if methods_artifacts:
        logger.info("Methods writing artifacts: %s", methods_artifacts)
    else:
        logger.info("Methods writing skipped or failed.")

    # Step 8: Main Results writing（需要 experiment_extraction.json + innovation_synthesis*.json）
    if not experiment_items:
        logger.info("No experiment items extracted; skip Step 8.")
        return

    main_results_artifacts = await run_main_results_writing_step(
        step_inputs=step_inputs,
        main_results_agent=main_results_agent,
        temperature=main_results_temperature,
        max_tokens=main_results_max_tokens,
        model=main_results_model,
    )
    if main_results_artifacts:
        logger.info("Main results writing artifacts: %s", main_results_artifacts)
    else:
        logger.info("Main results writing skipped or failed.")


if __name__ == "__main__":
    _load_local_env_file()
    # asyncio.run(main_run_step_7_only())
    # asyncio.run(main_run_step_6_only())
    # asyncio.run(main_run_step_8_only())
    asyncio.run(main_run_step_9_only())
    # start=time
    # asyncio.run(step_3_step4())
    # asyncio.run(
    #     main_run_steps_5_to_8(
    #         session_folder=Path(
    #             r"E:\pycharm_project\software_idea\academic draft agentic_workflow\app\core\workflows\output\2025_12_5\session_20251205_175558_006f8492"
    #         )
    #     )
    # )

