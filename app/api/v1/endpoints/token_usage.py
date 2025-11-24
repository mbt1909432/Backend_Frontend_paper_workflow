"""Token 使用统计 API 端点"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional
from datetime import datetime, timedelta
from app.api.deps_auth import get_current_backend_user
from app.db.database import get_db
from app.db.models import User, TokenUsage
from app.utils.logger import logger
from pydantic import BaseModel


router = APIRouter()


class TokenUsageSummary(BaseModel):
    """Token 使用统计摘要"""
    total_prompt_tokens: int
    total_completion_tokens: int
    total_tokens: int
    record_count: int
    
    class Config:
        from_attributes = True


class TokenUsageByStage(BaseModel):
    """按阶段统计的 Token 使用"""
    stage: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    record_count: int


class TokenUsageByModel(BaseModel):
    """按模型统计的 Token 使用"""
    model: Optional[str]
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    record_count: int


class TokenUsageDetail(BaseModel):
    """Token 使用详情"""
    id: str
    session_id: Optional[str]
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    model: Optional[str]
    stage: Optional[str]
    created_at: datetime
    
    class Config:
        from_attributes = True


class TokenUsageResponse(BaseModel):
    """Token 使用统计响应"""
    summary: TokenUsageSummary
    by_stage: List[TokenUsageByStage]
    by_model: List[TokenUsageByModel]
    recent_records: List[TokenUsageDetail]
    token_balance: int  # 用户当前token余额


class TokenBalanceResponse(BaseModel):
    """Token余额响应"""
    token_balance: int
    is_overdraft: bool  # 是否欠费


@router.get("/summary", response_model=TokenUsageResponse)
async def get_token_usage_summary(
    days: Optional[int] = 30,
    current_user: User = Depends(get_current_backend_user),
    db: Session = Depends(get_db)
):
    """
    获取用户的 Token 使用统计
    
    Args:
        days: 统计最近多少天的数据（默认30天）
        current_user: 当前登录用户
        db: 数据库会话
        
    Returns:
        Token 使用统计信息
    """
    try:
        # 计算起始时间
        start_date = datetime.utcnow() - timedelta(days=days)
        
        # 基础查询：当前用户的数据
        query = db.query(TokenUsage).filter(
            TokenUsage.user_id == current_user.id,
            TokenUsage.created_at >= start_date
        )
        
        # 汇总统计
        summary_result = query.with_entities(
            func.sum(TokenUsage.prompt_tokens).label('total_prompt_tokens'),
            func.sum(TokenUsage.completion_tokens).label('total_completion_tokens'),
            func.sum(TokenUsage.total_tokens).label('total_tokens'),
            func.count(TokenUsage.id).label('record_count')
        ).first()
        
        summary = TokenUsageSummary(
            total_prompt_tokens=int(summary_result.total_prompt_tokens or 0),
            total_completion_tokens=int(summary_result.total_completion_tokens or 0),
            total_tokens=int(summary_result.total_tokens or 0),
            record_count=int(summary_result.record_count or 0)
        )
        
        # 按阶段统计
        stage_results = query.with_entities(
            TokenUsage.stage,
            func.sum(TokenUsage.prompt_tokens).label('prompt_tokens'),
            func.sum(TokenUsage.completion_tokens).label('completion_tokens'),
            func.sum(TokenUsage.total_tokens).label('total_tokens'),
            func.count(TokenUsage.id).label('record_count')
        ).group_by(TokenUsage.stage).all()
        
        by_stage = [
            TokenUsageByStage(
                stage=stage or "unknown",
                prompt_tokens=int(prompt_tokens or 0),
                completion_tokens=int(completion_tokens or 0),
                total_tokens=int(total_tokens or 0),
                record_count=int(record_count or 0)
            )
            for stage, prompt_tokens, completion_tokens, total_tokens, record_count in stage_results
        ]
        
        # 按模型统计
        model_results = query.with_entities(
            TokenUsage.model,
            func.sum(TokenUsage.prompt_tokens).label('prompt_tokens'),
            func.sum(TokenUsage.completion_tokens).label('completion_tokens'),
            func.sum(TokenUsage.total_tokens).label('total_tokens'),
            func.count(TokenUsage.id).label('record_count')
        ).group_by(TokenUsage.model).all()
        
        by_model = [
            TokenUsageByModel(
                model=model,
                prompt_tokens=int(prompt_tokens or 0),
                completion_tokens=int(completion_tokens or 0),
                total_tokens=int(total_tokens or 0),
                record_count=int(record_count or 0)
            )
            for model, prompt_tokens, completion_tokens, total_tokens, record_count in model_results
        ]
        
        # 最近的记录（最近20条）
        recent_records = query.order_by(TokenUsage.created_at.desc()).limit(20).all()
        recent_details = [
            TokenUsageDetail(
                id=record.id,
                session_id=record.session_id,
                prompt_tokens=record.prompt_tokens,
                completion_tokens=record.completion_tokens,
                total_tokens=record.total_tokens,
                model=record.model,
                stage=record.stage,
                created_at=record.created_at
            )
            for record in recent_records
        ]
        
        # 获取用户当前token余额
        db.refresh(current_user)
        token_balance = current_user.token_balance or 0
        is_overdraft = token_balance < 0
        
        return TokenUsageResponse(
            summary=summary,
            by_stage=by_stage,
            by_model=by_model,
            recent_records=recent_details,
            token_balance=token_balance
        )
        
    except Exception as e:
        logger.error(f"Error getting token usage summary: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error getting token usage summary: {str(e)}")


@router.get("/all", response_model=List[TokenUsageDetail])
async def get_all_token_usage(
    limit: Optional[int] = 100,
    offset: Optional[int] = 0,
    current_user: User = Depends(get_current_backend_user),
    db: Session = Depends(get_db)
):
    """
    获取用户的所有 Token 使用记录（分页）
    
    Args:
        limit: 每页记录数（默认100）
        offset: 偏移量（默认0）
        current_user: 当前登录用户
        db: 数据库会话
        
    Returns:
        Token 使用记录列表
    """
    try:
        records = db.query(TokenUsage).filter(
            TokenUsage.user_id == current_user.id
        ).order_by(TokenUsage.created_at.desc()).offset(offset).limit(limit).all()
        
        return [
            TokenUsageDetail(
                id=record.id,
                session_id=record.session_id,
                prompt_tokens=record.prompt_tokens,
                completion_tokens=record.completion_tokens,
                total_tokens=record.total_tokens,
                model=record.model,
                stage=record.stage,
                created_at=record.created_at
            )
            for record in records
        ]
    except Exception as e:
        logger.error(f"Error getting token usage records: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error getting token usage records: {str(e)}")


@router.get("/balance", response_model=TokenBalanceResponse)
async def get_token_balance(
    current_user: User = Depends(get_current_backend_user),
    db: Session = Depends(get_db)
):
    """
    获取用户当前的 Token 余额
    
    Args:
        current_user: 当前登录用户
        db: 数据库会话
        
    Returns:
        Token余额信息
    """
    try:
        db.refresh(current_user)
        token_balance = current_user.token_balance or 0
        is_overdraft = token_balance < 0
        
        return TokenBalanceResponse(
            token_balance=token_balance,
            is_overdraft=is_overdraft
        )
    except Exception as e:
        logger.error(f"Error getting token balance: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error getting token balance: {str(e)}")

