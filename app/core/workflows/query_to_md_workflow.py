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
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.core.agents.query_rewrite_agent import QueryRewriteAgent
from app.core.agents.vision_agent import VisionAgent
from app.core.agents.methodology_extraction_agent import MethodologyExtractionAgent
from app.core.agents.experiment_extraction_agent import ExperimentExtractionAgent
from app.core.agents.innovation_synthesis_agent import InnovationSynthesisAgent
from app.core.agents.writing.methods_writing_agent import MethodsWritingAgent
from app.core.agents.writing.main_results_writing_agent import MainResultsWritingAgent
from app.core.workflows.postprocess_steps import (
    SessionStepInputs,
    run_pdf_ocr_step,
    run_markdown_emit_step,
    run_innovation_synthesis_step,
    run_methodology_extraction_step,
    run_experiment_extraction_step,
    run_methods_writing_step,
    run_main_results_writing_step,
    _load_local_env_file,
)
from app.config.settings import settings
from app.services.arxiv_service import search_and_download, ArxivPaperMetadata
from app.services.embedding_service import EmbeddingService
from app.services.anthropic_service import AnthropicService
from app.services.openai_service import OpenAIService
from app.utils.file_manager import create_session_folder, save_artifact
from app.utils.logger import logger
from app.utils.pdf_converter import pdf_to_pngs


def _mask_secret(secret: Optional[str]) -> str:
    """Mask long secrets before logging."""
    if not secret:
        return "None"
    if len(secret) <= 8:
        return f"{secret[:2]}***"
    return f"{secret[:4]}...{secret[-4:]}"


class QueryToMarkdownWorkflow:
    """
    Query → Markdown 工作流

    当前实现的 6 个阶段：
    - rewrite: 使用 QueryRewriteAgent 生成 4 条检索短句，落盘 rewrite.json
    - search:  对每条检索短句执行 arXiv 搜索与下载，生成 raw_pdfs/ 与 papers_manifest.json
    - ingest_pdf: 对 manifest 中 PDF 执行 PDF→PNG→OCR，生成 processed/paper_{idx}/ 目录与 pdf_processing.json
    - emit_md: 根据 OCR 文本与 metadata 生成 markdown/paper_*.md 与 summary/index.md、markdown_emit.json
    - extract_methodology_and_experiment: 从生成的 Markdown 文件中并行提取 problem statement & methodology 以及 experiments，生成对应 markdown 与 artifact JSON 文件
    - innovation_synthesis: 基于提取的 methodology 进行创新点综合
    """

    def __init__(
        self,
        query_rewrite_agent: QueryRewriteAgent,
        vision_agent: VisionAgent,
        methodology_extraction_agent: Optional[MethodologyExtractionAgent] = None,
        experiment_extraction_agent: Optional[ExperimentExtractionAgent] = None,
        innovation_agent: Optional[InnovationSynthesisAgent] = None,
        methods_writing_agent: Optional[MethodsWritingAgent] = None,
        main_results_agent: Optional[MainResultsWritingAgent] = None,
        embedding_service: Optional[EmbeddingService] = None,
        max_concurrent_pdfs: int = 2,
        max_concurrent_pages: int = 5,
        max_pages_per_pdf: Optional[int] = 50,
    ):
        self.query_rewrite_agent = query_rewrite_agent
        self.vision_agent = vision_agent
        self.methodology_extraction_agent = methodology_extraction_agent
        self.experiment_extraction_agent = experiment_extraction_agent
        self.innovation_agent = innovation_agent
        self.methods_writing_agent = methods_writing_agent
        self.main_results_agent = main_results_agent
        self.embedding_service = embedding_service or EmbeddingService()
        self.max_concurrent_pdfs = max_concurrent_pdfs
        self.max_concurrent_pages = max_concurrent_pages
        self.max_pages_per_pdf = max_pages_per_pdf

    async def execute(
        self,
        original_query: str,
        session_id: Optional[str] = None,
        username: Optional[str] = None,
        target_paper_count: int = 12,
        per_keyword_max_results: int = 10,
        per_keyword_recent_limit: int = 3,
        skip_dblp_check: bool = False,
        innovation_keywords_override: Optional[List[str]] = None,
        innovation_run_count: int = 1,
        max_pages_per_pdf: Optional[int] = None,
        max_paper_age_years: Optional[int] = 2,
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

        logger.info(
            "Config: OpenAI key=%s base=%s model=%s",
            _mask_secret(settings.openai_api_key),
            settings.openai_api_base or "https://api.openai.com/v1",
            settings.openai_model,
        )
        logger.info(
            "Config: Anthropic key=%s base=%s model=%s",
            _mask_secret(settings.anthropic_api_key),
            settings.anthropic_api_base or "https://api.anthropic.com",
            settings.anthropic_model,
        )

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
        concat_query = " ".join(kw.strip() for kw in keywords if kw.strip())
        if concat_query:
            logger.info(
                "Constructed concat_query (%d chars) for embedding ranking.",
                len(concat_query),
            )
        else:
            logger.warning(
                "concat_query is empty (no rewrite keywords). Will fall back to time-based selection."
            )

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
                delay_seconds = 3  # 3秒延迟
                logger.info(f"等待 {delay_seconds} 秒后处理下一个关键词...")
                time.sleep(delay_seconds)

        # 去重
        unique_by_id: Dict[str, ArxivPaperMetadata] = {}
        for p in all_papers:
            unique_by_id[p.arxiv_id] = p

        deduped_papers = list(unique_by_id.values())
        logger.info("Deduped papers: %d -> %d", len(all_papers), len(deduped_papers))

        def _to_naive(dt: datetime) -> datetime:
            return dt.replace(tzinfo=None) if dt.tzinfo else dt

        # 可选的时间窗口过滤
        cutoff_date: Optional[datetime] = None
        filtered_by_age: List[ArxivPaperMetadata] = deduped_papers
        if max_paper_age_years is not None and max_paper_age_years > 0:
            cutoff_date = datetime.utcnow() - timedelta(days=365 * max_paper_age_years)
            filtered_by_age = [
                p
                for p in deduped_papers
                if p.published and _to_naive(p.published) >= cutoff_date
            ]
        logger.info(
                "Age filter applied: <= %d years (cutoff=%s). %d papers remain.",
                max_paper_age_years,
                cutoff_date.isoformat(),
                len(filtered_by_age),
            )

        # 如果过滤后数量不足，则补齐旧论文
        shortlisted: List[ArxivPaperMetadata] = list(filtered_by_age)
        if len(shortlisted) < target_paper_count:
            logger.info(
                "Only %d papers after age filter; padding with older ones to reach %d target.",
                len(shortlisted),
                target_paper_count,
            )
            seen_ids = {p.arxiv_id for p in shortlisted}
            for p in deduped_papers:
                if p.arxiv_id in seen_ids:
                    continue
                shortlisted.append(p)
                seen_ids.add(p.arxiv_id)
                if len(shortlisted) >= target_paper_count:
                    break

        def _published_ts(paper: ArxivPaperMetadata) -> float:
            if not paper.published:
                return 0.0
            try:
                return paper.published.timestamp()
            except Exception:
                return 0.0

        ranking_strategy = "published_date"
        embedding_model_name: Optional[str] = None

        # 嵌入重排（若配置且 concat_query 可用）
        if (
            concat_query
            and shortlisted
            and self.embedding_service
            and self.embedding_service.is_configured
        ):
            try:
                ranking_strategy = "embedding"
                embedding_model_name = self.embedding_service.model
                paper_payloads = []
                for paper in shortlisted:
                    summary_snippet = (paper.summary or "")[:1500]
                    payload = f"{paper.title}\n\n{summary_snippet}"
                    paper_payloads.append(payload)

                embeddings = self.embedding_service.embed_texts(
                    [concat_query] + paper_payloads
                )
                query_embedding = embeddings[0]
                paper_embeddings = embeddings[1:]
                for paper, embedding in zip(shortlisted, paper_embeddings):
                    paper.relevance_score = self.embedding_service.cosine_similarity(
                        query_embedding,
                        embedding,
                    )
                shortlisted.sort(
                    key=lambda p: (
                        p.relevance_score is not None,
                        p.relevance_score or -1.0,
                        _published_ts(p),
                    ),
                    reverse=True,
                )
                logger.info(
                    "Embedding-based ranking applied to %d papers (model=%s).",
                    len(shortlisted),
                    embedding_model_name,
                )
            except Exception as exc:  # noqa: BLE001
                ranking_strategy = "published_date"
                embedding_model_name = None
                logger.exception("Embedding ranking failed, fallback to date: %s", exc)

        if ranking_strategy == "published_date":
            shortlisted.sort(key=_published_ts, reverse=True)

        top_papers = shortlisted[:target_paper_count]

        status = "ok" if len(top_papers) >= target_paper_count else "insufficient"

        logger.info(
            "arXiv search summary: total_raw=%d, total_deduped=%d, "
            "selected_for_ocr=%d, status=%s, ranking=%s",
            len(all_papers),
            len(deduped_papers),
            len(top_papers),
            status,
            ranking_strategy,
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
            "total_after_age_filter": len(filtered_by_age),
             "target_paper_count": target_paper_count,
            "concat_query": concat_query,
            "ranking_strategy": ranking_strategy,
            "embedding_model": embedding_model_name,
            "max_paper_age_years": max_paper_age_years,
            "age_filter_cutoff": cutoff_date.isoformat() if cutoff_date else None,
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
        papers_manifest, pdf_processing_results, pdf_processing_artifact_path = (
            await run_pdf_ocr_step(
                session_folder=session_folder,
                vision_agent=self.vision_agent,
                max_concurrent_pdfs=self.max_concurrent_pdfs,
                max_concurrent_pages=self.max_concurrent_pages,
                max_pages_per_pdf=(
                    max_pages_per_pdf
                    if max_pages_per_pdf is not None
                    else self.max_pages_per_pdf
                ),
            )
        )

        # -------------------------
        # Step 4: Markdown 生成
        # -------------------------
        logger.info("Step 4: Emit Markdown files from OCR text")

        markdown_items, markdown_emit_artifact_path, index_md_path = (
            await run_markdown_emit_step(
                session_folder=session_folder,
                papers_manifest=papers_manifest,
            )
        )

        step_inputs = SessionStepInputs(
            session_folder=session_folder,
            generated_dir=generated_dir,
            artifact_dir=artifact_dir,
            markdown_items=markdown_items,
            keywords=keywords,
        )

        # -------------------------
        # Step 5: Problem Statement & Methodology 提取 + Experiment 提取（并行执行）
        # -------------------------
        methodology_extraction_artifact_path: Optional[str] = None
        methodology_items: List[Dict[str, Any]] = []
        experiment_extraction_artifact_path: Optional[str] = None
        experiment_items: List[Dict[str, Any]] = []

        if self.methodology_extraction_agent is not None or self.experiment_extraction_agent is not None:
            logger.info(
                "Step 5: Extract problem statements & methodologies + experiments from Markdown files (parallel)"
            )

            has_methodology = self.methodology_extraction_agent is not None
            has_experiment = self.experiment_extraction_agent is not None

            # 准备并行任务列表（只加入真实需要执行的任务）
            gather_tasks = []
            if has_methodology:
                gather_tasks.append(
                    run_methodology_extraction_step(
                        step_inputs=step_inputs,
                        methodology_agent=self.methodology_extraction_agent,
                        max_concurrent_tasks=self.max_concurrent_pdfs,
                    )
                )
            if has_experiment:
                gather_tasks.append(
                    run_experiment_extraction_step(
                        step_inputs=step_inputs,
                        experiment_agent=self.experiment_extraction_agent,
                        max_concurrent_tasks=self.max_concurrent_pdfs,
                    )
                )

            # 并行执行
            results = await asyncio.gather(*gather_tasks, return_exceptions=True)

            # 处理结果，顺序与任务添加顺序一致
            result_idx = 0
            if has_methodology:
                try:
                    result = results[result_idx]
                    result_idx += 1
                    if isinstance(result, Exception):
                        logger.error("Step 5 methodology extraction failed: %s", result)
                    else:
                        (
                            methodology_extraction_artifact_path,
                            methodology_items,
                        ) = result
                        logger.info(
                            "Methodology artifact: %s",
                            methodology_extraction_artifact_path,
                        )
                except Exception as e:  # noqa: BLE001
                    logger.error("Error processing methodology result: %s", e)

            if has_experiment:
                try:
                    result = results[result_idx]
                    if isinstance(result, Exception):
                        logger.error("Step 5 experiment extraction failed: %s", result)
                    else:
                        (
                            experiment_extraction_artifact_path,
                            experiment_items,
                        ) = result
                        logger.info(
                            "Experiment artifact: %s",
                            experiment_extraction_artifact_path,
                        )
                except Exception as e:  # noqa: BLE001
                    logger.error("Error processing experiment result: %s", e)
        else:
            logger.info(
                "Step 5: Skipped (methodology_extraction_agent and experiment_extraction_agent not provided)"
            )

        # -------------------------
        # Step 6: Innovation synthesis agent（3-paper requirement）
        # -------------------------
        innovation_artifact_paths: List[str] = []
        if self.innovation_agent is not None:
            if not methodology_items:
                logger.warning(
                    "Innovation agent skipped: methodology step produced 0 eligible entries."
                )
            else:
                innovation_artifact_paths = await run_innovation_synthesis_step(
                    step_inputs=step_inputs,
                    methodology_items=methodology_items,
                    innovation_agent=self.innovation_agent,
                    override_keywords=innovation_keywords_override,
                    run_count=innovation_run_count,
                )
        else:
            logger.info("Step 6: Skipped (innovation_agent not provided)")

        # -------------------------
        # Step 7: Methods writing (LaTeX Methods section)
        # -------------------------
        methods_writing_artifacts: List[str] = []
        if self.methods_writing_agent is not None:
            if not innovation_artifact_paths:
                logger.info(
                    "Step 7: Skipped (no innovation_synthesis artifacts produced in Step 6)."
                )
            else:
                methods_writing_artifacts = await run_methods_writing_step(
                    step_inputs=step_inputs,
                    methods_writing_agent=self.methods_writing_agent,
                    temperature=0.7,
                    max_tokens=20000,
                )
        else:
            logger.info("Step 7: Skipped (methods_writing_agent not provided)")

        # -------------------------
        # Step 8: Main Results writing (LaTeX Main Results section)
        # -------------------------
        main_results_writing_artifacts: List[str] = []
        if self.main_results_agent is not None:
            if not experiment_items:
                logger.info(
                    "Step 8: Skipped (no experiment_items produced in Step 5 experiment extraction)."
                )
            elif not innovation_artifact_paths:
                logger.info(
                    "Step 8: Skipped (no innovation_synthesis artifacts to pair with experiments)."
                )
            else:
                main_results_writing_artifacts = (
                    await run_main_results_writing_step(
                        step_inputs=step_inputs,
                        main_results_agent=self.main_results_agent,
                        temperature=0.6,
                        max_tokens=40000,
                        model=None,
                    )
                )
        else:
            logger.info("Step 8: Skipped (main_results_agent not provided)")

        return {
            "session_id": session_id,
            "session_folder": str(session_folder),
            "rewrite_artifact": str(rewrite_artifact_path),
            "papers_manifest": str(manifest_path),
            "pdf_processing_artifact": str(pdf_processing_artifact_path),
            "markdown_emit_artifact": str(markdown_emit_artifact_path),
            "index_md": str(index_md_path),
            "methodology_extraction_artifact": methodology_extraction_artifact_path,
            "experiment_extraction_artifact": experiment_extraction_artifact_path,
            "methodology_items": methodology_items,
            "experiment_items": experiment_items,
            "innovation_artifacts": innovation_artifact_paths,
            "innovation_artifact": innovation_artifact_paths[0] if innovation_artifact_paths else None,
            "methods_writing_artifacts": methods_writing_artifacts,
            "main_results_writing_artifacts": main_results_writing_artifacts,
            "status": status,
        }


_VISION_TEST_IMAGE_PATH = Path(__file__).resolve().parents[3] / "lab" /"img.png" #"arxiv_2506.06962v3_page_18.png"


async def _test_anthropic_connectivity(anthropic_service: AnthropicService) -> bool:
    """
    发送一个极小的 messages.create 请求，快速验证 Anthropic API 是否可用。
    遇到无效 token/网络错误时提前终止 main 测试，避免整条流水线失败到 OCR 阶段才发现。
    """
    logger.info("Running Anthropic connectivity test...")
    try:
        await anthropic_service.messages_create(
            messages=[{"role": "user", "content": "Ping. Reply with PONG."}],
            temperature=0,
            max_tokens=5,
            model=settings.anthropic_model,
            system="You are a simple health-check bot. Respond with 'PONG'.",
        )
        logger.info("Anthropic connectivity test succeeded.")
        return True
    except Exception as exc:
        logger.error("Anthropic connectivity test failed: %s", exc)
        return False


async def _test_vision_agent(vision_agent: VisionAgent) -> bool:
    """
    使用 lab/1.png 调用 VisionAgent.analyze_image，验证 Anthropic 读图接口连通性。
    图片内容为项目内置示例，仅用于确认 API 可接受图片输入并返回文本。
    """
    logger.info("Running Anthropic vision (image/OCR) test...")
    if not _VISION_TEST_IMAGE_PATH.exists():
        logger.error("Vision test image not found: %s", _VISION_TEST_IMAGE_PATH)
        return False
    try:
        test_image_bytes = _VISION_TEST_IMAGE_PATH.read_bytes()
        result = await vision_agent.analyze_image(
            text_prompt="如果你看得到图片 回复pong",
            images=[test_image_bytes],
            temperature=0,
            max_tokens=10,
        )
        logger.info("Vision test succeeded. Response😀: %s", result)
        return True
    except Exception as exc:
        logger.error("Anthropic vision test failed: %s", exc)
        return False


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
    start_time = time.perf_counter()
    try:
        #test_query="""sci二区[领域需求]Autonomous driving safety"""

        # test_query="""sci二区[领域需求]AI safety protection algorithms"""

        # test_query="""Cloud computing + autonomous vehicles"""
#         test_query="""Adaptive Multi-Agent Embodied AI with Cross-Domain Visual Planning
#
#
# Current embodied AI systems cannot integrate visual understanding, cross-domain planning, and multi-agent coordination, limiting their ability to perform complex real-world tasks that require both physical actions and digital information retrieval.
#
#
# We solve the problem of fragmented embodied AI systems that cannot handle complex real-world tasks requiring visual understanding, web information, and coordinated actions. Current methods fail because they use fixed visual processing that misses temporal dynamics, make poor decisions about when to switch between physical and digital actions, and lack fault tolerance in multi-agent scenarios. Our method works in three stages: (1) Adaptive visual processing that samples video frames at 1-10fps based on motion detection and uses curriculum learning to adjust training difficulty, (2) Confidence-based cross-domain planning that calculates uncertainty scores to decide when to switch between physical actions and web queries, and (3) Fault-tolerant multi-agent coordination with heartbeat monitoring that detects agent failures in 5 seconds and reassigns tasks automatically. To implement this, we extend VideoLLaMA3 with adaptive sampling, add entropy-based confidence estimation to cross-domain planners, and build heartbeat monitoring into ROS 2 agent frameworks. We test on cooking tasks (using recipes from web), navigation with real-time map data, and warehouse coordination scenarios using AI2-THOR simulation and real robot platforms. The system needs PyTorch, ROS 2, web API access, 12GB GPU memory, and takes 2-3 days to train on video datasets with multi-agent interaction logs. Success is measured by task completion rate, domain switching accuracy, and system uptime during agent failures."""


        # test_query="""logistics: A Multi-Agent Predictive QptimizationFramework"""
        # test_query = """Autonomous driving safety"""
        # test_query = """AI safety protection algorithms"""
        test_query = """Data Science Applications in Social Networks and Advertising: A Causal Inference Approach"""
        test_username = "2025_12_4"
        test_session_id: Optional[str] = None  # None 时会自动生成，格式：session_{timestamp}_{uuid}

        _load_local_env_file()

        # 构造依赖
        openai_service = OpenAIService()
        query_agent = QueryRewriteAgent(openai_service=openai_service)
        methodology_agent = MethodologyExtractionAgent(openai_service=openai_service)
        experiment_agent = ExperimentExtractionAgent(openai_service=openai_service)
        innovation_agent = InnovationSynthesisAgent(openai_service=openai_service)
        methods_writing_agent = MethodsWritingAgent(openai_service=openai_service)
        main_results_agent = MainResultsWritingAgent(openai_service=openai_service)

        anthropic_service = AnthropicService()
        vision_agent = VisionAgent(anthropic_service=anthropic_service)


        if not await _test_anthropic_connectivity(anthropic_service):
            logger.error("Abort workflow run due to Anthropic connectivity failure.")
            return
        if not await _test_vision_agent(vision_agent):
            logger.error("Abort workflow run due to Anthropic vision failure.")
            return

        workflow = QueryToMarkdownWorkflow(
            query_rewrite_agent=query_agent,
            vision_agent=vision_agent,
            methodology_extraction_agent=methodology_agent,
            # experiment_extraction_agent=experiment_agent,#TODO：提取很慢 提取问题 还有reference防止提取
            innovation_agent=innovation_agent,
            # methods_writing_agent=methods_writing_agent,
            # main_results_agent=main_results_agent,
            max_concurrent_pdfs=2,
            max_concurrent_pages=2,  # 每篇论文同时处理的页面数
        )

        result = await workflow.execute(
            original_query=test_query,
            session_id=test_session_id,  # None 时自动生成，如：session_20251127_112630_748edba5
            username=test_username,
            target_paper_count=3,  # 最后需要的数量（去重后按时间排序取前 N 篇）
            per_keyword_max_results=10,  # 每个关键词最大的搜索结果
            per_keyword_recent_limit=10,  # 每个关键词只考虑最近 N 篇
            skip_dblp_check=True,  # 设置为 True 可跳过 DBLP 检查（会下载更多论文，但使用 arXiv BibTeX）
            max_paper_age_years=3
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
        if result.get("experiment_extraction_artifact"):
            logger.info("experiment_extraction_artifact: %s", result["experiment_extraction_artifact"])
        innovation_artifacts = result.get("innovation_artifacts") or []
        if innovation_artifacts:
            logger.info("innovation_artifacts: %s", innovation_artifacts)
    finally:
        elapsed = time.perf_counter() - start_time
        logger.info(
            "Query→Markdown workflow total runtime: %.2f seconds (≈%.2f minutes)",
            elapsed,
            elapsed / 60,
        )


if __name__ == "__main__":
    asyncio.run(main())


