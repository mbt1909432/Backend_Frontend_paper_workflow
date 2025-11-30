from __future__ import annotations

import asyncio
from typing import List, Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy.orm import Session

from app.api.deps import get_crawl_service
from app.api.deps_auth import get_current_admin_user
from app.db.database import get_db
from app.db.models import User, ArxivCrawlRun, ArxivPaper
from app.db.repositories import ArxivRepository
from app.services.crawler_service import MonthlyArxivSyncService


router = APIRouter()


class ArxivPaperOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    arxiv_id: str
    title: Optional[str] = None
    authors: Optional[str] = None
    subjects: Optional[str] = None
    abstract: Optional[str] = None
    detail_title: Optional[str] = None
    detail_dateline: Optional[str] = None
    algorithm_phrase: Optional[List[str]] = Field(default=None)
    metadata: Optional[dict] = None
    created_at: datetime

    @classmethod
    def from_orm_obj(cls, obj: ArxivPaper) -> "ArxivPaperOut":
        data = cls.model_validate(obj)
        data.metadata = obj.metadata_json
        # algorithm_phrase 可能是字符串，转为 list
        phrase = obj.algorithm_phrase
        if isinstance(phrase, list):
            data.algorithm_phrase = phrase
        elif isinstance(phrase, str):
            data.algorithm_phrase = [phrase]
        else:
            data.algorithm_phrase = None
        return data


class CrawlRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    run_month: str
    status: str
    started_at: datetime
    finished_at: Optional[datetime] = None
    duration_seconds: Optional[int] = None
    total_papers: int
    new_papers_count: int
    hot_phrases: Optional[List[str]] = None
    log: Optional[str] = None


class PaginatedPapersResponse(BaseModel):
    total: int
    items: List[ArxivPaperOut]


@router.get("/latest", response_model=CrawlRunOut)
def get_latest_run(db: Session = Depends(get_db)) -> CrawlRunOut:
    repo = ArxivRepository(db)
    run = repo.get_latest_run()
    if not run:
        raise HTTPException(status_code=404, detail="No crawl runs found")
    return CrawlRunOut.model_validate(run)


@router.get("/papers", response_model=PaginatedPapersResponse)
def list_papers(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, gt=0, le=100),
    keyword: Optional[str] = Query(default=None, description="标题/摘要模糊搜索"),
    db: Session = Depends(get_db),
) -> PaginatedPapersResponse:
    repo = ArxivRepository(db)
    total, items = repo.list_papers(skip=skip, limit=limit, keyword=keyword)
    mapped = [ArxivPaperOut.from_orm_obj(item) for item in items]
    return PaginatedPapersResponse(total=total, items=mapped)


@router.post("/trigger")
async def trigger_manual_run(
    service: MonthlyArxivSyncService = Depends(get_crawl_service),
    _: User = Depends(get_current_admin_user),
):
    if service.is_running():
        raise HTTPException(status_code=409, detail="Crawler is already running")
    asyncio.create_task(service.run_once())
    return {"detail": "Arxiv crawl triggered"}


