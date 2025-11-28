from __future__ import annotations

"""
Query → Markdown 工作流的前两步（初版）：
- 调用 QueryRewriteAgent 把原始 query 重写为 4 条完整检索短句
- 对每个检索短句调用 arxiv_service.search_and_download
- 写出 raw_pdfs 目录与 summary/papers_manifest.json

后续 PDF → 文本 与 Markdown 生成可以在此基础上逐步扩展。
"""

import json
import random
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.core.agents.query_rewrite_agent import QueryRewriteAgent
from app.core.agents.vision_agent import VisionAgent
from app.core.agents.methodology_extraction_agent import MethodologyExtractionAgent
from app.core.agents.innovation_synthesis_agent import InnovationSynthesisAgent
from app.core.workflows.postprocess_steps import (
    SessionStepInputs,
    run_innovation_synthesis_step,
    run_methodology_extraction_step,
)
from app.services.arxiv_service import search_and_download, ArxivPaperMetadata
from app.services.anthropic_service import AnthropicService
from app.services.openai_service import OpenAIService
from app.utils.file_manager import create_session_folder, save_artifact
from app.utils.logger import logger
from app.utils.pdf_converter import pdf_to_pngs


class QueryToMarkdownWorkflow:
    """
    Query → Markdown 工作流

    当前实现的 5 个阶段：
    - rewrite: 使用 QueryRewriteAgent 生成 4 条检索短句，落盘 rewrite.json
    - search:  对每条检索短句执行 arXiv 搜索与下载，生成 raw_pdfs/ 与 papers_manifest.json
    - ingest_pdf: 对 manifest 中 PDF 执行 PDF→PNG→OCR，生成 processed/paper_{idx}/ 目录与 pdf_processing.json
    - emit_md: 根据 OCR 文本与 metadata 生成 markdown/paper_*.md 与 summary/index.md、markdown_emit.json
    - extract_methodology: 从生成的 Markdown 文件中提取 problem statement 与 methodology，生成对应 markdown 与 methodology_extraction.json
    """

    def __init__(
        self,
        query_rewrite_agent: QueryRewriteAgent,
        vision_agent: VisionAgent,
        methodology_extraction_agent: Optional[MethodologyExtractionAgent] = None,
        innovation_agent: Optional[InnovationSynthesisAgent] = None,
        max_concurrent_pdfs: int = 2,
        max_concurrent_pages: int = 5,
    ):
        self.query_rewrite_agent = query_rewrite_agent
        self.vision_agent = vision_agent
        self.methodology_extraction_agent = methodology_extraction_agent
        self.innovation_agent = innovation_agent
        self.max_concurrent_pdfs = max_concurrent_pdfs
        self.max_concurrent_pages = max_concurrent_pages

    async def execute(
        self,
        original_query: str,
        session_id: Optional[str] = None,
        username: Optional[str] = None,
        target_paper_count: int = 12,
        per_keyword_max_results: int = 10,
        per_keyword_recent_limit: int = 3,
        skip_dblp_check: bool = False,
    ) -> Dict[str, Any]:
        # 执行完整流程：
        # 1) QueryRewriteAgent 生成 4 条检索短句
        # 2) 对每条短句调用 arXiv 搜索与下载，生成 manifest
        # 3) 对 manifest 中 PDF 执行 PDF→PNG→OCR
        # 4) 生成 Markdown 与 summary/index.md
        # 5) 从 Markdown 文件中提取 problem statement 与 methodology（如果 agent 已提供）

        # 1. 创建 session 目录（对齐现有 file_manager 逻辑）
        session_folder = create_session_folder(session_id, username=username)
        session_id = session_folder.name

        logger.info("=" * 80)
        logger.info(f"Starting Query→Markdown Workflow (rewrite + arxiv) - Session: {session_id}")
        logger.info("=" * 80)

        if target_paper_count < 3:
            logger.warning(
                "target_paper_count=%d is below minimum requirement (3). Overriding to 3 for downstream innovation stage.",
                target_paper_count,
            )
            target_paper_count = 3

        artifact_dir = session_folder / "artifact"
        generated_dir = session_folder / "generated"
        artifact_dir.mkdir(parents=True, exist_ok=True)
        generated_dir.mkdir(parents=True, exist_ok=True)

        # -------------------------
        # Step 1: Query Rewrite
        # -------------------------
        logger.info("Step 1: Query rewrite with QueryRewriteAgent")
        rewrite_result = await self.query_rewrite_agent.generate_rewrite(
            original_query=original_query
        )

        rewrite_json = rewrite_result.get("json") or {}
        keywords: List[str] = rewrite_json.get("keywords") or []

        # 将 rewrite 结果存为 artifact/rewrite.json（对齐文档约定，复用 file_manager.save_artifact）
        rewrite_artifact_path = save_artifact(
            session_folder=session_folder,
            stage_name="rewrite",
            artifact_data={
                "original_query": original_query,
                "keywords": keywords,
                "agent_payload": rewrite_json,
                "usage": rewrite_result.get("usage"),
            },
        )
        logger.info("✓ rewrite.json saved at %s", rewrite_artifact_path)

        # -------------------------
        # Step 2: arXiv 搜索与下载
        # -------------------------
        logger.info("Step 2: arXiv search & download for rewritten queries")

        raw_pdfs_root = session_folder / "raw_pdfs"
        raw_pdfs_root.mkdir(parents=True, exist_ok=True)

        all_papers: List[ArxivPaperMetadata] = []

        for i, kw in enumerate(keywords):
            keyword_dir_name = kw.replace(" ", "_")[:80] or "keyword"
            keyword_outdir = raw_pdfs_root / keyword_dir_name
            logger.info("Running arXiv search for keyword: %s (outdir=%s)", kw, keyword_outdir)

            papers = search_and_download(
                keyword=kw,
                outdir=keyword_outdir,
                max_results=per_keyword_max_results,
                recent_limit=per_keyword_recent_limit,
                filter_surveys=True,
                skip_dblp_check=skip_dblp_check,
            )
            if skip_dblp_check:
                logger.info(
                    "arXiv search finished for keyword '%s': %d papers downloaded (DBLP check skipped)",
                    kw,
                    len(papers),
                )
            else:
                logger.info(
                    "arXiv search finished for keyword '%s': %d papers passed DBLP & downloaded",
                    kw,
                    len(papers),
                )
            all_papers.extend(papers)
            
            # 在关键词之间添加延迟（除了最后一个）
            if i < len(keywords) - 1:
                import time
                delay_seconds = 3  # 3秒延迟
                logger.info(f"等待 {delay_seconds} 秒后处理下一个关键词...")
                time.sleep(delay_seconds)

        # 去重并按发布时间排序，保留最近 target_paper_count 篇
        unique_by_id: Dict[str, ArxivPaperMetadata] = {}
        for p in all_papers:
            unique_by_id[p.arxiv_id] = p

        deduped_papers = list(unique_by_id.values())
        deduped_papers.sort(key=lambda p: p.published or 0, reverse=True)
        top_papers = deduped_papers[:target_paper_count]

        status = "ok"
        if len(top_papers) < target_paper_count:
            status = "insufficient"

        logger.info(
            "arXiv search summary: total_raw=%d, total_deduped=%d, selected_for_ocr=%d, status=%s",
            len(all_papers),
            len(deduped_papers),
            len(top_papers),
            status,
        )

        manifest_items: List[Dict[str, Any]] = [
            p.to_manifest_dict() for p in top_papers
        ]

        papers_manifest = {
            "original_query": original_query,
            "rewrite_keywords": keywords,
            "per_keyword_max_results": per_keyword_max_results,
            "per_keyword_recent_limit": per_keyword_recent_limit,
            "total_found": len(all_papers),
            "total_deduped": len(deduped_papers),
             "target_paper_count": target_paper_count,
            "papers": manifest_items,
            "status": status,
        }

        # 存到 generated/papers_manifest.json（对齐文档规划）
        manifest_path = generated_dir / "papers_manifest.json"
        manifest_path.write_text(
            json.dumps(papers_manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.info("✓ papers_manifest.json saved at %s", manifest_path)

        # -------------------------
        # Step 3: PDF → 文本（OCR）
        # -------------------------
        logger.info("Step 3: PDF → Text via pdf_to_pngs + VisionAgent")

        processed_root = session_folder / "processed"
        processed_root.mkdir(parents=True, exist_ok=True)

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
            except Exception as e:
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
            result["page_count"] = len(png_paths)

            # 页面级并发处理：使用 asyncio.gather 并发处理所有页面
            page_semaphore = asyncio.Semaphore(self.max_concurrent_pages)
            sorted_png_paths = sorted(png_paths)

            async def process_single_page(page_idx: int, png_path: str) -> tuple[int, str, dict, Optional[str]]:
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
                        ocr_result = await self.vision_agent.extract_text_from_image(
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
                    except Exception as e:
                        logger.exception(
                            "OCR failed on paper %s page %d: %s", paper_id, page_idx, e
                        )
                        return (page_idx, "", {}, f"OCR failed on page {page_idx}: {e}")

            # 并发处理所有页面
            logger.info(
                "Starting concurrent OCR for paper %s: %d pages (max_concurrent=%d)",
                paper_id,
                len(sorted_png_paths),
                self.max_concurrent_pages,
            )
            
            page_results = await asyncio.gather(
                *[
                    process_single_page(page_idx, png_path)
                    for page_idx, png_path in enumerate(sorted_png_paths, start=1)
                ],
                return_exceptions=True,
            )

            # 按页面索引排序并处理结果（确保页面顺序正确）
            page_texts: List[str] = [""] * len(sorted_png_paths)
            failed_pages: List[tuple[int, str]] = []
            
            # 过滤异常并排序（按 page_idx）
            valid_results = []
            for page_result in page_results:
                if isinstance(page_result, Exception):
                    logger.error(
                        "Unexpected exception in page processing: %s", page_result
                    )
                    continue
                valid_results.append(page_result)
            
            # 按 page_idx 排序，确保页面顺序正确
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

        # 控制并发度，对 12 篇论文做 OCR
        semaphore = asyncio.Semaphore(self.max_concurrent_pdfs)

        async def sem_task(idx: int, paper: Dict[str, Any]) -> Dict[str, Any]:
            async with semaphore:
                return await process_single_paper(idx, paper)

        pdf_processing_results: List[Dict[str, Any]] = await asyncio.gather(
            *[
                sem_task(idx, paper)
                for idx, paper in enumerate(papers_manifest["papers"], start=1)
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
        logger.info("✓ papers_manifest.json updated with OCR info at %s", manifest_path)

        # -------------------------
        # Step 4: Markdown 生成
        # -------------------------
        logger.info("Step 4: Emit Markdown files from OCR text")

        markdown_dir = generated_dir / "markdown"
        markdown_dir.mkdir(parents=True, exist_ok=True)

        markdown_items: List[Dict[str, Any]] = []

        for idx, paper in enumerate(papers_manifest["papers"], start=1):
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
            except Exception as e:
                logger.exception(
                    "Failed to read OCR full text for paper %s: %s",
                    paper.get("arxiv_id"),
                    e,
                )
                paper["status"] = "failed"
                continue

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
                ocr_text,
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
        index_md_path = generated_dir / "index.md"
        index_lines: List[str] = []
        index_lines.append(f"# Query → Markdown Summary")
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

        for idx, paper in enumerate(papers_manifest["papers"], start=1):
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
                f"> 注意：共找到 {len(deduped_papers)} 篇去重论文，少于目标 {target_paper_count} 篇，status = {status}。"
            )

        failed_papers = [
            (i, p)
            for i, p in enumerate(papers_manifest["papers"], start=1)
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

        step_inputs = SessionStepInputs(
            session_folder=session_folder,
            generated_dir=generated_dir,
            artifact_dir=artifact_dir,
            markdown_items=markdown_items,
            keywords=keywords,
        )

        # -------------------------
        # Step 5: Problem Statement & Methodology 提取
        # -------------------------
        methodology_extraction_artifact_path: Optional[str] = None
        methodology_items: List[Dict[str, Any]] = []
        if self.methodology_extraction_agent is not None:
            logger.info("Step 5: Extract problem statements & methodologies from Markdown files")
            methodology_extraction_artifact_path, methodology_items = await run_methodology_extraction_step(
                step_inputs=step_inputs,
                methodology_agent=self.methodology_extraction_agent,
                max_concurrent_tasks=self.max_concurrent_pdfs,
            )
        else:
            logger.info("Step 5: Skipped (methodology_extraction_agent not provided)")

        # -------------------------
        # Step 6: Innovation synthesis agent（3-paper requirement）
        # -------------------------
        innovation_artifact_path: Optional[str] = None
        if self.innovation_agent is not None:
            if not methodology_items:
                logger.warning("Innovation agent skipped: methodology step produced 0 eligible entries.")
            else:
                innovation_artifact_path = await run_innovation_synthesis_step(
                    step_inputs=step_inputs,
                    methodology_items=methodology_items,
                    innovation_agent=self.innovation_agent,
                )
        else:
            logger.info("Step 6: Skipped (innovation_agent not provided)")

        return {
            "session_id": session_id,
            "session_folder": str(session_folder),
            "rewrite_artifact": str(rewrite_artifact_path),
            "papers_manifest": str(manifest_path),
            "pdf_processing_artifact": str(pdf_processing_artifact_path),
            "markdown_emit_artifact": str(markdown_emit_artifact_path),
            "index_md": str(index_md_path),
            "methodology_extraction_artifact": methodology_extraction_artifact_path,
            "innovation_artifact": innovation_artifact_path,
            "status": status,
        }


async def main() -> None:
    """
    简单本地测试入口：直接在当前脚本内跑一次 Query → Markdown 工作流。
    不使用 CLI/argparse，方便在 IDE 中运行和断点调试。
    
    参数设置说明：
    ============
    1. session_id 和输出位置的关系：
       - 如果 test_session_id = None，系统会自动生成格式为 session_{timestamp}_{uuid} 的 session_id
       - 例如：session_20251127_112630_748edba5（2025年11月27日 11:26:30，UUID前8位）
       - session_id 决定了所有输出文件的存储位置：{output_dir}/{username}/{session_id}/
       - 所有生成的文件（PDF、BibTeX、Markdown等）都会保存在这个 session 文件夹下
    
    2. skip_dblp_check 参数的影响：
       - skip_dblp_check=False（默认）：只下载在 DBLP 中有匹配的论文，使用 DBLP 的 BibTeX
       - skip_dblp_check=True：跳过 DBLP 检查，下载所有符合条件的论文，使用 arXiv 生成的 BibTeX
       - 设置为 True 时，可能会下载更多论文（因为不限制 DBLP 匹配），但 BibTeX 质量可能较低
    
    3. 论文数量控制参数：
       - target_paper_count=4：最终保留的论文数量（去重后，按发布时间排序，取前 N 篇）
       - per_keyword_max_results=3：每个关键词搜索时返回的最大结果数
       - per_keyword_recent_limit=3：每个关键词只考虑最近 N 篇论文
       - 实际流程：4个关键词 × 每个最多3篇 = 最多12篇 → 去重 → 按时间排序 → 取前4篇
    
    4. 输出文件位置（以 session_20251127_112630_748edba5 为例）：
       - raw_pdfs/：下载的原始 PDF 文件
       - generated/papers_manifest.json：论文清单（包含元数据、路径等）
       - generated/markdown/：生成的 Markdown 文件
       - generated/index.md：汇总索引文件
       - artifact/：中间产物（rewrite.json、pdf_processing.json 等）
    """
    # 你可以根据需要在这里修改测试用的 query / username / session_id
    test_query = "【需求3】Robot Learning(e.g. CoRL, RSS, etc.), Machine Learning or Computer Vision for robotics (ICRL) Learning based and data-driven model for robot manipulations or plans Affordance prediction, manipulation plans, imitation learning, reinforcement learning for robotics LLM or NLP for robotics."
    test_username = "dev_tester"
    test_session_id: Optional[str] = None  # None 时会自动生成，格式：session_{timestamp}_{uuid}

    # 构造依赖
    openai_service = OpenAIService()
    query_agent = QueryRewriteAgent(openai_service=openai_service)
    methodology_agent = MethodologyExtractionAgent(openai_service=openai_service)
    innovation_agent = InnovationSynthesisAgent(openai_service=openai_service)

    anthropic_service = AnthropicService()
    vision_agent = VisionAgent(anthropic_service=anthropic_service)

    workflow = QueryToMarkdownWorkflow(
        query_rewrite_agent=query_agent,
        vision_agent=vision_agent,
        methodology_extraction_agent=methodology_agent,
        innovation_agent=innovation_agent,
        max_concurrent_pdfs=2,
        max_concurrent_pages=5,  # 每篇论文同时处理的页面数
    )

    result = await workflow.execute(
        original_query=test_query,
        session_id=test_session_id,  # None 时自动生成，如：session_20251127_112630_748edba5
        username=test_username,
        target_paper_count=3,  # 最后需要的数量（去重后按时间排序取前 N 篇）
        per_keyword_max_results=9,  # 每个关键词最大的搜索结果
        per_keyword_recent_limit=3,  # 每个关键词只考虑最近 N 篇
        skip_dblp_check=False,  # 设置为 True 可跳过 DBLP 检查（会下载更多论文，但使用 arXiv BibTeX）
    )

    logger.info("Query→Markdown workflow finished.")
    logger.info("Session folder: %s", result["session_folder"])
    logger.info("rewrite_artifact: %s", result["rewrite_artifact"])
    logger.info("papers_manifest: %s", result["papers_manifest"])
    logger.info("pdf_processing_artifact: %s", result["pdf_processing_artifact"])
    logger.info("markdown_emit_artifact: %s", result["markdown_emit_artifact"])
    logger.info("index_md: %s", result["index_md"])
    if result.get("methodology_extraction_artifact"):
        logger.info("methodology_extraction_artifact: %s", result["methodology_extraction_artifact"])
    if result.get("innovation_artifact"):
        logger.info("innovation_artifact: %s", result["innovation_artifact"])


if __name__ == "__main__":
    asyncio.run(main())


