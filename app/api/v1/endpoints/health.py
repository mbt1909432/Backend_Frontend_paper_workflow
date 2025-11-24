from fastapi import APIRouter
from typing import Dict


router = APIRouter()


@router.get("/health", response_model=Dict[str, str])
async def health_check():
    """健康检查端点"""
    return {"status": "healthy", "service": "academic_draft_agent"}

