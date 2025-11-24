"""认证API端点"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from app.db.database import get_db
from app.db.models import User
from app.core.security import verify_password, get_password_hash, create_access_token
from app.config.settings import settings
from app.utils.logger import logger

router = APIRouter()


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str
    is_admin: bool
    user_type: str


class UserResponse(BaseModel):
    id: str
    username: str
    is_admin: bool
    is_active: bool
    user_type: str
    max_concurrent_workflows: int
    created_at: str
    
    class Config:
        from_attributes = True


@router.post("/login", response_model=LoginResponse)
async def login(
    request: LoginRequest,
    db: Session = Depends(get_db)
):
    """用户登录"""
    # 检查是否是超级管理员
    if request.username == settings.admin_username_value:
        if request.password == settings.admin_password_value:
            # 检查数据库中是否存在超级管理员，如果不存在则创建
            admin_user = db.query(User).filter(User.username == settings.admin_username_value).first()
            if not admin_user:
                admin_user = User(
                    username=settings.admin_username_value,
                    password_hash=get_password_hash(settings.admin_password_value),
                    is_admin=True,
                    is_active=True,
                    user_type="backend"  # 管理员默认是后端用户
                )
                db.add(admin_user)
                db.commit()
                db.refresh(admin_user)
                logger.info(f"创建超级管理员用户: {settings.admin_username_value}")
            
            # 生成令牌
            access_token = create_access_token(data={"sub": admin_user.username})
            return LoginResponse(
                access_token=access_token,
                username=admin_user.username,
                is_admin=admin_user.is_admin,
                user_type=admin_user.user_type
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="用户名或密码错误"
            )
    
    # 普通用户登录
    user = db.query(User).filter(User.username == request.username).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误"
        )
    
    if not verify_password(request.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误"
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="用户已被禁用"
        )
    
    # 生成令牌
    access_token = create_access_token(data={"sub": user.username})
    return LoginResponse(
        access_token=access_token,
        username=user.username,
        is_admin=user.is_admin,
        user_type=user.user_type
    )


# 使用函数内导入来避免循环依赖
def _register_me_endpoint():
    """注册/me端点，避免循环导入"""
    from app.api.deps_auth import get_current_user
    
    @router.get("/me", response_model=UserResponse)
    async def get_current_user_info(
        current_user: User = Depends(get_current_user)
    ):
        """获取当前用户信息"""
        return UserResponse(
            id=current_user.id,
            username=current_user.username,
            is_admin=current_user.is_admin,
            is_active=current_user.is_active,
            user_type=current_user.user_type,
            max_concurrent_workflows=current_user.max_concurrent_workflows,
            created_at=current_user.created_at.isoformat()
        )

# 注册端点
_register_me_endpoint()
