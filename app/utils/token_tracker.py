"""Token 使用追踪工具"""
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session
from app.db.models import TokenUsage, User
from app.utils.logger import logger


def record_token_usage(
    db: Session,
    user_id: str,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    total_tokens: int = 0,
    model: Optional[str] = None,
    stage: Optional[str] = None,
    session_id: Optional[str] = None
) -> TokenUsage:
    """
    记录 token 使用情况到数据库
    
    Args:
        db: 数据库会话
        user_id: 用户 ID
        prompt_tokens: prompt token 数量
        completion_tokens: completion token 数量
        total_tokens: 总 token 数量（如果为0则自动计算）
        model: 模型名称
        stage: 使用场景（如 paper_overview, latex_paper 等）
        session_id: session ID
        
    Returns:
        TokenUsage 对象
    """
    try:
        # 如果 total_tokens 为0，自动计算
        if total_tokens == 0:
            total_tokens = prompt_tokens + completion_tokens
        
        token_usage = TokenUsage(
            user_id=user_id,
            session_id=session_id,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            model=model,
            stage=stage
        )
        
        db.add(token_usage)
        db.commit()
        db.refresh(token_usage)
        
        logger.info(
            f"Token usage recorded: user_id={user_id}, stage={stage}, "
            f"total_tokens={total_tokens}, model={model}"
        )
        
        return token_usage
    except Exception as e:
        logger.error(f"Failed to record token usage: {str(e)}")
        db.rollback()
        raise


def record_usage_from_dict(
    db: Session,
    user_id: str,
    usage_dict: Dict[str, Any],
    model: Optional[str] = None,
    stage: Optional[str] = None,
    session_id: Optional[str] = None
) -> TokenUsage:
    """
    从字典记录 token 使用情况
    
    Args:
        db: 数据库会话
        user_id: 用户 ID
        usage_dict: 包含 token 使用信息的字典，格式如：
            {
                "prompt_tokens": int,
                "completion_tokens": int,
                "total_tokens": int
            }
        model: 模型名称
        stage: 使用场景
        session_id: session ID
        
    Returns:
        TokenUsage 对象
    """
    return record_token_usage(
        db=db,
        user_id=user_id,
        prompt_tokens=usage_dict.get("prompt_tokens", 0),
        completion_tokens=usage_dict.get("completion_tokens", 0),
        total_tokens=usage_dict.get("total_tokens", 0),
        model=model,
        stage=stage,
        session_id=session_id
    )


def settle_token_usage(
    db: Session,
    user_id: str,
    total_tokens: int,
    session_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    结算token使用，从用户余额中扣除（允许欠费）
    
    Args:
        db: 数据库会话
        user_id: 用户 ID
        total_tokens: 本次流程使用的总token数
        session_id: 可选的 session ID（用于日志）
        
    Returns:
        包含结算结果的字典：
        {
            "success": bool,
            "previous_balance": int,
            "tokens_used": int,
            "new_balance": int,
            "is_overdraft": bool  # 是否欠费
        }
    """
    try:
        # 获取用户
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            logger.error(f"User not found: {user_id}")
            raise ValueError(f"User not found: {user_id}")
        
        previous_balance = user.token_balance
        new_balance = previous_balance - total_tokens
        is_overdraft = new_balance < 0
        
        # 更新用户余额（允许负数，即欠费）
        user.token_balance = new_balance
        db.commit()
        db.refresh(user)
        
        logger.info(
            f"Token settled: user_id={user_id}, session_id={session_id}, "
            f"previous_balance={previous_balance}, tokens_used={total_tokens}, "
            f"new_balance={new_balance}, is_overdraft={is_overdraft}"
        )
        
        return {
            "success": True,
            "previous_balance": previous_balance,
            "tokens_used": total_tokens,
            "new_balance": new_balance,
            "is_overdraft": is_overdraft
        }
    except Exception as e:
        logger.error(f"Failed to settle token usage: {str(e)}")
        db.rollback()
        raise

