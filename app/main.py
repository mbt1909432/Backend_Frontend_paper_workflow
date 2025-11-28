from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config.settings import settings, proxy_manager
from app.api.v1.router import api_router
from app.utils.logger import logger
from app.db.database import engine, Base
from app.utils.provider_health import check_llm_connectivity


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
    
    # 启动时检查代理可用性
    logger.info("Checking proxy availability...")
    proxy_available = await proxy_manager.is_proxy_available(force_check=True)
    if proxy_available:
        logger.info(f"✓ Proxy enabled and available: {settings.proxy_url}")
    else:
        if settings.proxy_enabled:
            logger.warning(f"✗ Proxy enabled but not available: {settings.proxy_url}")
        else:
            logger.info("✓ Proxy disabled")
    
    # 启动时检查 LLM 服务可用性
    provider_status = await check_llm_connectivity()
    for provider, status in provider_status.items():
        logger.info(f"{provider.capitalize()} status -> {status['status']}: {status['detail']}")
    
    # 缓存检查结果，便于后续健康检查接口读取
    app.state.provider_health = provider_status
    app.state.proxy_available = proxy_available


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

