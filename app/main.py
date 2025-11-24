from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config.settings import settings
from app.api.v1.router import api_router
from app.utils.logger import logger
from app.db.database import engine, Base


# 创建 FastAPI 应用
app = FastAPI(
    title="ResearchFlow",
    description="基于 FastAPI + OpenAI SDK 的 Agent 服务，支持流式响应",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS 中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境应限制具体域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册 API 路由
app.include_router(api_router, prefix="/api/v1")


@app.on_event("startup")
async def startup_event():
    """应用启动事件"""
    logger.info("Application starting up...")
    logger.info(f"OpenAI Model: {settings.openai_model}")
    logger.info(f"Server running on {settings.host}:{settings.port}")
    
    # 创建数据库表
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("Database tables created/verified successfully")
    except Exception as e:
        logger.error(f"Failed to create database tables: {e}")
        raise


@app.on_event("shutdown")
async def shutdown_event():
    """应用关闭事件"""
    logger.info("Application shutting down...")


@app.get("/")
async def root():
    """根路径"""
    return {
        "message": "ResearchFlow API",
        "version": "1.0.0",
        "docs": "/docs"
    }

