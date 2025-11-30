"""数据库模型"""
from sqlalchemy import Column, String, Integer, DateTime, Boolean, Text, ForeignKey, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.database import Base
import uuid


class User(Base):
    """用户模型"""
    __tablename__ = "users"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    username = Column(String(100), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    is_admin = Column(Boolean, default=False, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    user_type = Column(String(20), default="backend", nullable=False)  # frontend: 前端用户(销售人员对接), backend: 后端用户(业务员工)
    token_balance = Column(Integer, default=1000000, nullable=False)  # 初始token余额：100万
    max_concurrent_workflows = Column(Integer, default=10, nullable=False)  # 最大并发workflow数，默认10
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    
    # 关系
    sessions = relationship("Session", back_populates="user", cascade="all, delete-orphan")
    tasks = relationship("Task", back_populates="user", cascade="all, delete-orphan")
    token_usages = relationship("TokenUsage", back_populates="user", cascade="all, delete-orphan")


class Session(Base):
    """Session模型"""
    __tablename__ = "sessions"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(String(255), unique=True, nullable=False, index=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    
    # 关系
    user = relationship("User", back_populates="sessions")
    tasks = relationship("Task", back_populates="session", cascade="all, delete-orphan")


class Task(Base):
    """任务模型"""
    __tablename__ = "tasks"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    task_id = Column(String(255), unique=True, nullable=False, index=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    session_id = Column(String, ForeignKey("sessions.id"), nullable=True, index=True)
    
    # 任务名称（用户可编辑）
    name = Column(String(255), nullable=True)
    
    # 任务信息
    document = Column(Text, nullable=True)
    user_info = Column(Text, nullable=True)
    has_outline = Column(Boolean, default=False, nullable=False)
    has_existing_tex = Column(Boolean, default=False, nullable=False)
    
    # 任务状态
    status = Column(String(50), default="pending", nullable=False, index=True)  # pending, running, completed, failed, deleting
    progress = Column(Integer, default=0, nullable=False)  # 0-100
    
    # 结果数据（JSON格式存储）
    result_data = Column(JSON, nullable=True)
    
    # 错误信息
    error = Column(Text, nullable=True)
    
    # 当前步骤
    current_step = Column(String(255), nullable=True)
    
    # 日志（JSON格式存储字符串数组）
    logs = Column(JSON, nullable=True)  # 存储为字符串数组
    
    # 文件信息（JSON格式存储文件元数据）
    pdf_file_info = Column(JSON, nullable=True)  # {name, size, type} 或 null
    image_files_info = Column(JSON, nullable=True)  # [{name, size, type}, ...] 或 []
    
    # 配置参数
    temperature = Column(String(50), nullable=True)
    max_tokens = Column(String(50), nullable=True)
    model = Column(String(100), nullable=True)
    
    # 时间戳
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    
    # 关系
    user = relationship("User", back_populates="tasks")
    session = relationship("Session", back_populates="tasks")


class TokenUsage(Base):
    """Token 使用记录模型"""
    __tablename__ = "token_usage"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    session_id = Column(String(255), nullable=True, index=True)  # 可选的 session ID
    
    # Token 使用信息
    prompt_tokens = Column(Integer, default=0, nullable=False)
    completion_tokens = Column(Integer, default=0, nullable=False)
    total_tokens = Column(Integer, default=0, nullable=False)
    
    # 模型信息
    model = Column(String(100), nullable=True, index=True)
    
    # 使用场景
    stage = Column(String(100), nullable=True, index=True)  # paper_overview, latex_paper, requirement_checklist, chat, etc.
    
    # 时间戳
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    
    # 关系
    user = relationship("User", back_populates="token_usages")


class ArxivCrawlRun(Base):
    """arXiv 爬虫执行记录"""
    __tablename__ = "arxiv_crawl_runs"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    run_month = Column(String(7), nullable=False, index=True)
    status = Column(String(20), default="running", nullable=False, index=True)
    started_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    duration_seconds = Column(Integer, nullable=True)
    error_message = Column(Text, nullable=True)
    total_papers = Column(Integer, default=0, nullable=False)
    new_papers_count = Column(Integer, default=0, nullable=False)
    hot_phrases = Column(JSON, nullable=True)
    log = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    papers = relationship("ArxivPaper", back_populates="crawl_run", cascade="all, delete-orphan")


class ArxivPaper(Base):
    """爬取的 arXiv 论文"""
    __tablename__ = "arxiv_papers"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    crawl_run_id = Column(String, ForeignKey("arxiv_crawl_runs.id"), nullable=False, index=True)
    arxiv_id = Column(String(32), unique=True, nullable=False, index=True)
    title = Column(Text, nullable=True)
    authors = Column(Text, nullable=True)
    subjects = Column(Text, nullable=True)
    abstract = Column(Text, nullable=True)
    detail_title = Column(Text, nullable=True)
    detail_dateline = Column(String(255), nullable=True)
    algorithm_phrase = Column(JSON, nullable=True)
    # metadata is a reserved Declarative attribute; store actual column as metadata_json
    metadata_json = Column("metadata", JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    crawl_run = relationship("ArxivCrawlRun", back_populates="papers")