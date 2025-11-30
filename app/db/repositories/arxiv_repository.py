"""数据库仓储：arXiv 爬虫"""
from __future__ import annotations

from typing import Iterable, List, Optional, Tuple
from datetime import datetime

from sqlalchemy.orm import Session, selectinload
from sqlalchemy import or_
from sqlalchemy.dialects.postgresql import insert

from app.db.models import ArxivCrawlRun, ArxivPaper


class ArxivRepository:
    """封装 arXiv 爬虫相关的数据库操作"""

    def __init__(self, session: Session):
        self.session = session

    # Crawl run operations
    def create_crawl_run(self, payload: dict) -> ArxivCrawlRun:
        run = ArxivCrawlRun(**payload)
        self.session.add(run)
        self.session.flush()
        return run

    def update_crawl_run(self, run_id: str, **fields) -> None:
        fields["updated_at"] = fields.get("updated_at", datetime.utcnow())
        self.session.query(ArxivCrawlRun).filter(ArxivCrawlRun.id == run_id).update(fields)

    # Paper operations
    def bulk_upsert_papers(self, run_id: str, papers: Iterable[dict]) -> int:
        rows = [self._map_paper_payload(run_id, paper) for paper in papers]
        rows = [row for row in rows if row]
        if not rows:
            return 0

        stmt = insert(ArxivPaper).values(rows)
        update_cols = {
            "crawl_run_id": stmt.excluded.crawl_run_id,
            "title": stmt.excluded.title,
            "authors": stmt.excluded.authors,
            "subjects": stmt.excluded.subjects,
            "abstract": stmt.excluded.abstract,
            "detail_title": stmt.excluded.detail_title,
            "detail_dateline": stmt.excluded.detail_dateline,
            "algorithm_phrase": stmt.excluded.algorithm_phrase,
            "updated_at": datetime.utcnow(),
        }
        stmt = stmt.on_conflict_do_update(
            index_elements=[ArxivPaper.arxiv_id],
            set_=update_cols,
        )
        result = self.session.execute(stmt)
        return result.rowcount or len(rows)

    def list_papers(self, skip: int = 0, limit: int = 20, keyword: Optional[str] = None) -> Tuple[int, List[ArxivPaper]]:
        query = self.session.query(ArxivPaper).order_by(ArxivPaper.created_at.desc())
        if keyword:
            pattern = f"%{keyword}%"
            query = query.filter(
                or_(
                    ArxivPaper.title.ilike(pattern),
                    ArxivPaper.abstract.ilike(pattern),
                    ArxivPaper.arxiv_id.ilike(pattern),
                )
            )
        total = query.count()
        items = query.offset(skip).limit(limit).all()
        return total, items

    # Read operations
    def get_latest_run(self) -> Optional[ArxivCrawlRun]:
        return (
            self.session.query(ArxivCrawlRun)
            .options(selectinload(ArxivCrawlRun.papers))
            .order_by(ArxivCrawlRun.started_at.desc())
            .first()
        )

    def list_hot_phrases(self, limit: int = 5) -> List[str]:
        run = (
            self.session.query(ArxivCrawlRun)
            .filter(ArxivCrawlRun.hot_phrases.isnot(None))
            .order_by(ArxivCrawlRun.started_at.desc())
            .first()
        )
        if not run:
            return []
        phrases = run.hot_phrases or []
        if isinstance(phrases, list):
            return phrases[:limit]
        return []

    # Helpers
    @staticmethod
    def _map_paper_payload(run_id: str, paper: dict) -> Optional[dict]:
        arxiv_id = paper.get("arxiv_id")
        if not arxiv_id:
            return None
        authors = paper.get("authors")
        if isinstance(authors, list):
            authors = ", ".join(authors)
        algorithm_phrase = paper.get("algorithm_phrase")
        if isinstance(algorithm_phrase, str):
            algorithm_phrase = [algorithm_phrase]

        metadata = {
            key: paper.get(key)
            for key in (
                "arxiv_url",
                "pdf_url",
                "comments",
                "journal_ref",
                "detail_fetched_at",
            )
        }
        # remove empty values
        metadata = {k: v for k, v in metadata.items() if v is not None}

        return {
            "crawl_run_id": run_id,
            "arxiv_id": arxiv_id,
            "title": paper.get("title"),
            "authors": authors,
            "subjects": paper.get("subjects"),
            "abstract": paper.get("abstract"),
            "detail_title": paper.get("detail_title"),
            "detail_dateline": paper.get("detail_dateline"),
            "algorithm_phrase": algorithm_phrase,
        }


