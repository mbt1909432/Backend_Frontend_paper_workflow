from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

# TODO: Move ArxivCrawler/save_to_json into app/services (see ticket #?)
from lab.crawl_ai import ArxivCrawler, save_to_json

from app.config.settings import settings
from app.db.database import SessionLocal
from app.db.repositories import ArxivRepository
from app.utils.logger import setup_logger


logger = setup_logger("arxiv_crawl_service")


@dataclass
class CrawlResult:
    run_id: str
    status: str
    total_papers: int
    new_papers: int
    hot_phrases: List[str]
    duration_seconds: Optional[int]
    error: Optional[str] = None


class MonthlyArxivSyncService:
    """包装 lab/crawl_ai.py 的服务层，负责调度、持久化与日志。"""

    def __init__(
        self,
        session_factory=SessionLocal,
        crawler_cls=ArxivCrawler,
    ):
        self._session_factory = session_factory
        self._crawler_cls = crawler_cls
        self._lock = asyncio.Lock()

    async def run_once(self, *, persist: bool = True, output_path: Optional[str] = None) -> CrawlResult:
        if self._lock.locked():
            logger.warning("Arxiv crawler run skipped: another run is in progress")
            return CrawlResult(
                run_id="",
                status="skipped",
                total_papers=0,
                new_papers=0,
                hot_phrases=[],
                duration_seconds=None,
                error="run_in_progress",
            )

        async with self._lock:
            return await self._execute_run(persist=persist, output_path=output_path)

    def is_running(self) -> bool:
        return self._lock.locked()

    async def _execute_run(self, *, persist: bool, output_path: Optional[str]) -> CrawlResult:
        start_time = datetime.utcnow()
        session = None
        repo = None
        crawl_run = None

        if persist:
            session = self._session_factory()
            repo = ArxivRepository(session)
            run_month = start_time.strftime("%Y-%m")
            crawl_run = repo.create_crawl_run(
                {
                    "run_month": run_month,
                    "status": "running",
                    "started_at": start_time,
                    "log": None,
                }
            )
            session.commit()
            session.refresh(crawl_run)

        try:
            result = await self._launch_crawler()
            new_papers = result.get("new_papers") or []
            total_papers = result.get("total_papers") or 0
            hot_phrases = result.get("hot_phrases") or []
            if output_path:
                save_to_json(result, filename=output_path)

            if not persist:
                duration_seconds = int((datetime.utcnow() - start_time).total_seconds())
                logger.info(
                    "Arxiv crawler dry-run success: total=%s new=%s json=%s",
                    total_papers,
                    len(new_papers),
                    output_path or "N/A",
                )
                return CrawlResult(
                    run_id="",
                    status="success",
                    total_papers=total_papers,
                    new_papers=len(new_papers),
                    hot_phrases=hot_phrases if isinstance(hot_phrases, list) else [],
                    duration_seconds=duration_seconds,
                )

            repo.bulk_upsert_papers(crawl_run.id, new_papers)

            finished_at = datetime.utcnow()
            duration_seconds = int((finished_at - start_time).total_seconds())
            log_summary = self._build_log_summary(new_papers, hot_phrases)
            repo.update_crawl_run(
                crawl_run.id,
                status="success",
                finished_at=finished_at,
                duration_seconds=duration_seconds,
                total_papers=total_papers,
                new_papers_count=len(new_papers),
                hot_phrases=hot_phrases or None,
                log=log_summary,
            )
            session.commit()
            logger.info(
                "Arxiv crawler run success: run_id=%s total=%s new=%s",
                crawl_run.id,
                total_papers,
                len(new_papers),
            )
            return CrawlResult(
                run_id=crawl_run.id,
                status="success",
                total_papers=total_papers,
                new_papers=len(new_papers),
                hot_phrases=hot_phrases if isinstance(hot_phrases, list) else [],
                duration_seconds=duration_seconds,
            )
        except Exception as exc:  # noqa: BLE001
            if not persist:
                logger.exception("Arxiv crawler dry-run failed")
                duration = int((datetime.utcnow() - start_time).total_seconds())
                return CrawlResult(
                    run_id="",
                    status="failed",
                    total_papers=0,
                    new_papers=0,
                    hot_phrases=[],
                    duration_seconds=duration,
                    error=str(exc),
                )

            session.rollback()
            logger.exception("Arxiv crawler run failed: run_id=%s", crawl_run.id)
            finished_at = datetime.utcnow()
            repo.update_crawl_run(
                crawl_run.id,
                status="failed",
                finished_at=finished_at,
                error_message=str(exc),
            )
            session.commit()
            return CrawlResult(
                run_id=crawl_run.id,
                status="failed",
                total_papers=0,
                new_papers=0,
                hot_phrases=[],
                duration_seconds=int((finished_at - start_time).total_seconds()),
                error=str(exc),
            )
        finally:
            if session:
                session.close()

    async def _launch_crawler(self) -> Dict[str, Any]:
        crawler = self._build_crawler()
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, crawler.run)

    def _build_crawler(self) -> ArxivCrawler:
        crawler_kwargs = {
            "base_url": settings.arxiv_base_url,
            "max_papers": settings.arxiv_max_papers,
            "papers_per_page": settings.arxiv_papers_per_page,
            "use_proxy": settings.arxiv_use_proxy,
            "sleep_time": settings.arxiv_sleep_time,
            "fetch_details": settings.arxiv_fetch_details,
            "detail_sleep": settings.arxiv_detail_sleep,
            "existing_data_path": settings.arxiv_existing_data_path or "",
            "summarize_new": settings.arxiv_summarize_new,
            "summary_model": settings.arxiv_summary_model or settings.openai_model,
            "summary_temperature": settings.arxiv_summary_temperature,
            "summary_max_tokens": settings.arxiv_summary_max_tokens,
            "summary_sleep": settings.arxiv_summary_sleep,
            "summary_concurrency": settings.arxiv_summary_concurrency,
            "aggregate_hot": settings.arxiv_aggregate_hot,
            "hot_model": settings.arxiv_hot_model or settings.arxiv_summary_model or settings.openai_model,
            "hot_temperature": settings.arxiv_hot_temperature,
            "hot_max_tokens": settings.arxiv_hot_max_tokens,
            "hot_top_k": settings.arxiv_hot_top_k,
        }
        return self._crawler_cls(**crawler_kwargs)

    @staticmethod
    def _build_log_summary(new_papers: List[dict], hot_phrases: Any) -> str:
        parts = [
            f"new_papers={len(new_papers)}",
        ]
        if isinstance(hot_phrases, list) and hot_phrases:
            preview = ", ".join(hot_phrases[:5])
            parts.append(f"hot_phrases={preview}")
        return " | ".join(parts)


