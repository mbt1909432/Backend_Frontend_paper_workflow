from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from typing import Optional
import asyncio
import aiohttp
import logging


class Settings(BaseSettings):
    """应用配置"""
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"  # 忽略未定义的字段
    )
    
    # OpenAI 配置
    openai_api_key: str
    openai_api_base: Optional[str] = None  # 自定义 API endpoint（用于模型转发商）
    openai_model: str = "claude-sonnet-4-20250514"
    openai_temperature: float = 0.7
    openai_max_tokens: int = 30000
    
    # Anthropic 配置
    anthropic_api_key: Optional[str] = None
    anthropic_api_base: Optional[str] = None  # 自定义 API endpoint（用于模型转发商）
    anthropic_model: str = "claude-sonnet-4-20250514"
    anthropic_temperature: float = 0.7
    anthropic_max_tokens: int = 30000
    
    # 服务器配置
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = True
    
    # 日志配置
    log_level: str = "INFO"
    
    # 文件输出配置
    output_dir: str = "output"  # 输出目录，用于保存生成的文件
    
    # 代理配置
    proxy_enabled: bool = Field(default=True, description="是否启用代理")
    proxy_url: str = Field(default="http://127.0.0.1:7890", description="代理服务器地址")
    proxy_auto_detect: bool = Field(default=True, description="是否自动检测代理可用性")
    proxy_timeout: int = Field(default=10, description="代理检测超时时间（秒）")
    proxy_test_url: str = Field(default="https://www.google.com", description="用于测试代理的URL")
    
    # arXiv 爬虫与调度配置
    arxiv_base_url: str = Field(default="https://arxiv.org/list/cs.AI/recent", description="arXiv cs.AI 列表页")
    arxiv_max_papers: int = Field(default=25, description="最大爬取论文数量")
    arxiv_papers_per_page: int = Field(default=25, description="每页抓取的论文数")
    arxiv_use_proxy: bool = Field(default=True, description="抓取是否使用代理")
    arxiv_sleep_time: int = Field(default=2, description="翻页间隔秒数")
    arxiv_fetch_details: bool = Field(default=True, description="是否抓取详情页")
    arxiv_detail_sleep: int = Field(default=1, description="详情页抓取间隔秒数")
    arxiv_existing_data_path: Optional[str] = Field(default=None, description="历史数据文件路径，用于去重")
    arxiv_summarize_new: bool = Field(default=True, description="是否对新增论文执行 LLM 摘要")
    arxiv_summary_model: Optional[str] = Field(default=None, description="用于摘要的模型名称，默认跟随 openai_model")
    arxiv_summary_temperature: float = Field(default=0.3, description="摘要模型温度")
    arxiv_summary_max_tokens: int = Field(default=512, description="摘要模型最大 tokens")
    arxiv_summary_sleep: float = Field(default=0.0, description="摘要调用间歇秒数")
    arxiv_summary_concurrency: int = Field(default=5, description="摘要调用最大并发")
    arxiv_aggregate_hot: bool = Field(default=True, description="是否聚合热门算法词条")
    arxiv_hot_model: Optional[str] = Field(default=None, description="聚合热门短语的模型")
    arxiv_hot_temperature: float = Field(default=0.2, description="热门短语模型温度")
    arxiv_hot_max_tokens: int = Field(default=512, description="热门短语模型最大 tokens")
    arxiv_hot_top_k: int = Field(default=10, description="热门短语数量")
    scheduler_enabled: bool = Field(default=True, description="是否启用 APScheduler")
    scheduler_timezone: str = Field(default="Asia/Shanghai", description="调度器时区")
    arxiv_cron: str = Field(default="0 3 1 * *", description="arXiv 同步 cron 表达式")
    
    # 数据库配置 - 支持 db_* 或 POSTGRES_* 环境变量名
    db_user: Optional[str] = Field(default="postgres")
    db_password: Optional[str] = Field(default="postgres")
    db_host: Optional[str] = Field(default="localhost")
    db_port: Optional[int] = Field(default=5434)
    db_name: Optional[str] = Field(default="academic_workflow")
    
    # 也支持 POSTGRES_* 格式的环境变量（通过别名）
    postgres_user: Optional[str] = Field(default=None, alias="POSTGRES_USER")
    postgres_password: Optional[str] = Field(default=None, alias="POSTGRES_PASSWORD")
    postgres_db: Optional[str] = Field(default=None, alias="POSTGRES_DB")
    postgres_host: Optional[str] = Field(default=None, alias="POSTGRES_HOST")
    postgres_port: Optional[int] = Field(default=None, alias="POSTGRES_PORT")
    
    @property
    def database_url(self) -> str:
        """构建数据库连接URL"""
        # 优先使用 POSTGRES_*，否则使用 db_* 或默认值
        user = self.postgres_user or self.db_user or "postgres"
        password = self.postgres_password or self.db_password or "postgres"
        host = self.postgres_host or self.db_host or "localhost"
        port = self.postgres_port or self.db_port or 5432
        db = self.postgres_db or self.db_name or "academic_workflow"
        return f"postgresql://{user}:{password}@{host}:{port}/{db}"
    
    # JWT认证配置
    secret_key: str = Field(default="your-secret-key-change-in-production")
    algorithm: str = "HS256"
    access_token_expire_minutes: int = Field(default=60 * 24 * 7)  # 7天
    
    # 超级管理员配置 - 支持 admin_* 或 SUPER_ADMIN_* 环境变量名
    admin_username: Optional[str] = Field(default="admin")
    admin_password: Optional[str] = Field(default="admin123")
    
    # 也支持 SUPER_ADMIN_* 格式的环境变量（通过别名）
    super_admin_username: Optional[str] = Field(default=None, alias="SUPER_ADMIN_USERNAME")
    super_admin_password: Optional[str] = Field(default=None, alias="SUPER_ADMIN_PASSWORD")
    
    @property
    def admin_username_value(self) -> str:
        """获取管理员用户名（优先使用 SUPER_ADMIN_*，否则使用 admin_* 或默认值）"""
        return self.super_admin_username or self.admin_username or "admin"
    
    @property
    def admin_password_value(self) -> str:
        """获取管理员密码（优先使用 SUPER_ADMIN_*，否则使用 admin_* 或默认值）"""
        return self.super_admin_password or self.admin_password or "admin123"


class ProxyManager:
    """代理管理器"""
    
    def __init__(self, settings: Settings):
        self.settings = settings
        self.logger = logging.getLogger(__name__)
        self._proxy_available = None
        self._last_check_time = 0
        self._check_interval = 300  # 5分钟检查一次
    
    async def is_proxy_available(self, force_check: bool = False) -> bool:
        """检查代理是否可用"""
        import time
        current_time = time.time()
        
        # 如果不强制检查且在检查间隔内，返回缓存结果
        if not force_check and self._proxy_available is not None and (current_time - self._last_check_time) < self._check_interval:
            return self._proxy_available
        
        if not self.settings.proxy_enabled:
            self._proxy_available = False
            return False
        
        try:
            connector = aiohttp.TCPConnector()
            timeout = aiohttp.ClientTimeout(total=self.settings.proxy_timeout)
            
            async with aiohttp.ClientSession(
                connector=connector,
                timeout=timeout
            ) as session:
                async with session.get(
                    self.settings.proxy_test_url,
                    proxy=self.settings.proxy_url
                ) as response:
                    self._proxy_available = response.status == 200
                    self._last_check_time = current_time
                    
                    if self._proxy_available:
                        self.logger.info(f"✓ 代理可用: {self.settings.proxy_url}")
                    else:
                        self.logger.warning(f"✗ 代理响应异常: {response.status}")
                    
                    return self._proxy_available
                    
        except Exception as e:
            self._proxy_available = False
            self._last_check_time = current_time
            self.logger.warning(f"✗ 代理不可用: {self.settings.proxy_url} - {e}")
            return False
    
    def get_proxy_dict(self) -> dict:
        """获取代理配置字典（用于 requests 等库）"""
        if self._proxy_available:
            return {
                'http': self.settings.proxy_url,
                'https': self.settings.proxy_url
            }
        return {}
    
    def get_proxy_url(self) -> Optional[str]:
        """获取代理URL（用于 aiohttp 等库）"""
        return self.settings.proxy_url if self._proxy_available else None


# 全局配置实例
settings = Settings()

# 全局代理管理器实例
proxy_manager = ProxyManager(settings)


def reload_settings() -> Settings:
    """Reload settings from environment (in-place) so existing references stay valid."""
    global settings
    new_settings = Settings()
    for field_name, value in new_settings.model_dump().items():
        setattr(settings, field_name, value)

    # 重置代理管理器状态，使其使用新配置
    proxy_manager.settings = settings
    proxy_manager._proxy_available = None
    proxy_manager._last_check_time = 0
    return settings

