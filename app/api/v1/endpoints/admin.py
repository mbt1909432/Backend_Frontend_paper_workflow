"""管理员API端点"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from pydantic import BaseModel
from app.db.database import get_db
from app.db.models import User
from app.core.security import get_password_hash
from app.api.deps_auth import get_current_admin_user
from app.config.settings import settings
from app.utils.logger import logger

router = APIRouter()


class UserCreate(BaseModel):
    username: str
    password: str
    user_type: str = "backend"  # frontend: 前端用户, backend: 后端用户


class UserUpdate(BaseModel):
    password: str | None = None
    is_active: bool | None = None
    user_type: str | None = None


class TokenBalanceUpdate(BaseModel):
    token_balance: int


class MaxConcurrentWorkflowsUpdate(BaseModel):
    max_concurrent_workflows: int


class UserResponse(BaseModel):
    id: str
    username: str
    is_admin: bool
    is_active: bool
    user_type: str
    token_balance: int
    max_concurrent_workflows: int
    created_at: str
    
    class Config:
        from_attributes = True


@router.post("/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    user_data: UserCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user)
):
    """创建新用户"""
    # 检查用户名是否已存在
    existing_user = db.query(User).filter(User.username == user_data.username).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="用户名已存在"
        )
    
    # 验证user_type
    if user_data.user_type not in ["frontend", "backend"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="user_type必须是'frontend'或'backend'"
        )
    
    # 创建新用户
    new_user = User(
        username=user_data.username,
        password_hash=get_password_hash(user_data.password),
        is_admin=False,
        is_active=True,
        user_type=user_data.user_type
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    logger.info(f"管理员 {current_user.username} 创建了新用户: {user_data.username}")
    
    return UserResponse(
        id=new_user.id,
        username=new_user.username,
        is_admin=new_user.is_admin,
        is_active=new_user.is_active,
        user_type=new_user.user_type,
        token_balance=new_user.token_balance,
        max_concurrent_workflows=new_user.max_concurrent_workflows,
        created_at=new_user.created_at.isoformat()
    )


@router.get("/users", response_model=List[UserResponse])
async def list_users(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user)
):
    """列出所有用户"""
    users = db.query(User).all()
    return [
        UserResponse(
            id=user.id,
            username=user.username,
            is_admin=user.is_admin,
            is_active=user.is_active,
            user_type=user.user_type,
            token_balance=user.token_balance,
            max_concurrent_workflows=user.max_concurrent_workflows,
            created_at=user.created_at.isoformat()
        )
        for user in users
    ]


@router.get("/users/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user)
):
    """获取用户信息"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在"
        )
    return UserResponse(
        id=user.id,
        username=user.username,
        is_admin=user.is_admin,
        is_active=user.is_active,
        user_type=user.user_type,
        token_balance=user.token_balance,
        max_concurrent_workflows=user.max_concurrent_workflows,
        created_at=user.created_at.isoformat()
    )


@router.put("/users/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: str,
    user_data: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user)
):
    """更新用户信息"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在"
        )
    
    # 不能修改超级管理员
    if user.username == settings.admin_username_value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="不能修改超级管理员"
        )
    
    # 更新密码
    if user_data.password is not None:
        user.password_hash = get_password_hash(user_data.password)
    
    # 更新状态
    if user_data.is_active is not None:
        user.is_active = user_data.is_active
    
    # 更新用户类型
    if user_data.user_type is not None:
        if user_data.user_type not in ["frontend", "backend"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="user_type必须是'frontend'或'backend'"
            )
        user.user_type = user_data.user_type
    
    db.commit()
    db.refresh(user)
    
    logger.info(f"管理员 {current_user.username} 更新了用户: {user.username}")
    
    return UserResponse(
        id=user.id,
        username=user.username,
        is_admin=user.is_admin,
        is_active=user.is_active,
        user_type=user.user_type,
        token_balance=user.token_balance,
        max_concurrent_workflows=user.max_concurrent_workflows,
        created_at=user.created_at.isoformat()
    )


@router.patch("/users/{user_id}/token-balance", response_model=UserResponse)
async def update_user_token_balance(
    user_id: str,
    token_data: TokenBalanceUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user)
):
    """更新用户Token余额"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在"
        )
    
    old_balance = user.token_balance
    user.token_balance = token_data.token_balance
    db.commit()
    db.refresh(user)
    
    logger.info(
        f"管理员 {current_user.username} 更新了用户 {user.username} 的Token余额: "
        f"{old_balance} -> {user.token_balance}"
    )
    
    return UserResponse(
        id=user.id,
        username=user.username,
        is_admin=user.is_admin,
        is_active=user.is_active,
        user_type=user.user_type,
        token_balance=user.token_balance,
        max_concurrent_workflows=user.max_concurrent_workflows,
        created_at=user.created_at.isoformat()
    )


@router.patch("/users/{user_id}/max-concurrent-workflows", response_model=UserResponse)
async def update_user_max_concurrent_workflows(
    user_id: str,
    workflow_data: MaxConcurrentWorkflowsUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user)
):
    """更新用户最大并发workflow数"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在"
        )
    
    if workflow_data.max_concurrent_workflows < 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="最大并发workflow数必须大于0"
        )
    
    old_value = user.max_concurrent_workflows
    user.max_concurrent_workflows = workflow_data.max_concurrent_workflows
    db.commit()
    db.refresh(user)
    
    logger.info(
        f"管理员 {current_user.username} 更新了用户 {user.username} 的最大并发workflow数: "
        f"{old_value} -> {user.max_concurrent_workflows}"
    )
    
    return UserResponse(
        id=user.id,
        username=user.username,
        is_admin=user.is_admin,
        is_active=user.is_active,
        user_type=user.user_type,
        token_balance=user.token_balance,
        max_concurrent_workflows=user.max_concurrent_workflows,
        created_at=user.created_at.isoformat()
    )


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user)
):
    """删除用户"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在"
        )
    
    # 不能删除超级管理员
    if user.username == settings.admin_username_value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="不能删除超级管理员"
        )
    
    username = user.username
    db.delete(user)
    db.commit()
    
    logger.info(f"管理员 {current_user.username} 删除了用户: {username}")

