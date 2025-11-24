from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from typing import Optional


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
    openai_model: str = "gpt-4"
    openai_temperature: float = 0.7
    openai_max_tokens: int = 2000
    
    # Anthropic 配置
    anthropic_api_key: Optional[str] = None
    anthropic_api_base: Optional[str] = None  # 自定义 API endpoint（用于模型转发商）
    anthropic_model: str = "claude-sonnet-4-20250514"
    anthropic_temperature: float = 0.7
    anthropic_max_tokens: int = 4096
    
    # 服务器配置
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = True
    
    # 日志配置
    log_level: str = "INFO"
    
    # 文件输出配置
    output_dir: str = "output"  # 输出目录，用于保存生成的文件
    
    # 数据库配置 - 支持 db_* 或 POSTGRES_* 环境变量名
    db_user: Optional[str] = Field(default="postgres")
    db_password: Optional[str] = Field(default="postgres")
    db_host: Optional[str] = Field(default="localhost")
    db_port: Optional[int] = Field(default=5432)
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


# 全局配置实例
settings = Settings()

