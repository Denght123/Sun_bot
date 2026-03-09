from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Application
    app_name: str = Field(default="finance-news-bot-backend", alias="APP_NAME")
    app_env: str = Field(default="development", alias="APP_ENV")
    app_version: str = Field(default="0.1.0", alias="APP_VERSION")
    app_description: str = Field(default="finance news bot backend API", alias="APP_DESCRIPTION")
    app_host: str = Field(default="0.0.0.0", alias="APP_HOST")
    app_port: int = Field(default=8000, alias="APP_PORT")
    api_prefix: str = Field(default="/api", alias="API_PREFIX")
    timezone: str = Field(default="Asia/Shanghai", alias="TIMEZONE")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    # Auth / shared tokens
    admin_token: str = Field(default="change-me-admin-token", alias="ADMIN_TOKEN")
    sender_token: str = Field(default="change-me-sender-token", alias="SENDER_TOKEN")

    # Database
    database_url_override: str | None = Field(default=None, alias="DATABASE_URL")
    postgres_host: str = Field(default="postgres", alias="POSTGRES_HOST")
    postgres_port: int = Field(default=5432, alias="POSTGRES_PORT")
    postgres_db: str = Field(default="finance_news", alias="POSTGRES_DB")
    postgres_user: str = Field(default="finance_news", alias="POSTGRES_USER")
    postgres_password: str = Field(default="finance_news", alias="POSTGRES_PASSWORD")

    # Cache
    redis_url_override: str | None = Field(default=None, alias="REDIS_URL")
    redis_host: str = Field(default="redis", alias="REDIS_HOST")
    redis_port: int = Field(default=6379, alias="REDIS_PORT")
    redis_db: int = Field(default=0, alias="REDIS_DB")
    redis_password: str | None = Field(default=None, alias="REDIS_PASSWORD")

    # Scheduler / dispatch core
    scheduler_enabled: bool = Field(default=True, alias="SCHEDULER_ENABLED")
    scheduler_timezone: str | None = Field(default=None, alias="SCHEDULER_TIMEZONE")
    daily_dispatch_hour: int = Field(default=8, alias="DAILY_DISPATCH_HOUR")
    daily_dispatch_minute: int = Field(default=0, alias="DAILY_DISPATCH_MINUTE")
    dispatch_max_retry: int = Field(default=3, alias="DISPATCH_MAX_RETRY")
    dispatch_stale_timeout_seconds: int = Field(default=300, alias="DISPATCH_STALE_TIMEOUT_SECONDS")
    scheduler_startup_reconcile: bool = Field(default=True, alias="SCHEDULER_STARTUP_RECONCILE")
    scheduler_recovery_interval_seconds: int = Field(default=60, alias="SCHEDULER_RECOVERY_INTERVAL_SECONDS")
    scheduler_misfire_grace_seconds: int = Field(default=900, alias="SCHEDULER_MISFIRE_GRACE_SECONDS")

    # Primary delivery contract (WeCom-first; implementation remains follow-up work)
    dispatch_provider: str = Field(default="wecom_app", alias="DISPATCH_PROVIDER")
    dispatch_execution_mode: str = Field(default="backend", alias="DISPATCH_EXECUTION_MODE")
    wecom_enabled: bool = Field(default=True, alias="WECOM_ENABLED")
    wecom_api_base_url: str = Field(default="https://qyapi.weixin.qq.com/cgi-bin", alias="WECOM_API_BASE_URL")
    wecom_corp_id: str | None = Field(default=None, alias="WECOM_CORP_ID")
    wecom_agent_id: str | None = Field(default=None, alias="WECOM_AGENT_ID")
    wecom_secret: str | None = Field(default=None, alias="WECOM_SECRET")
    wecom_default_touser: str | None = Field(default=None, alias="WECOM_DEFAULT_TOUSER")
    wecom_default_toparty: str | None = Field(default=None, alias="WECOM_DEFAULT_TOPARTY")
    wecom_default_totag: str | None = Field(default=None, alias="WECOM_DEFAULT_TOTAG")
    wecom_message_type: str = Field(default="text", alias="WECOM_MESSAGE_TYPE")
    wecom_safe: int = Field(default=0, alias="WECOM_SAFE")
    wecom_token_refresh_buffer_seconds: int = Field(default=300, alias="WECOM_TOKEN_REFRESH_BUFFER_SECONDS")
    wecom_callback_enabled: bool = Field(default=False, alias="WECOM_CALLBACK_ENABLED")
    wecom_callback_token: str | None = Field(default=None, alias="WECOM_CALLBACK_TOKEN")
    wecom_callback_aes_key: str | None = Field(default=None, alias="WECOM_CALLBACK_AES_KEY")

    # Legacy sender-agent fallback
    dispatch_default_target_user: str = Field(default="my_wechat_id", alias="DISPATCH_DEFAULT_TARGET_USER")
    sender_online_threshold_seconds: int = Field(default=60, alias="SENDER_ONLINE_THRESHOLD_SECONDS")
    sender_degraded_threshold_seconds: int = Field(default=180, alias="SENDER_DEGRADED_THRESHOLD_SECONDS")
    sender_next_heartbeat_seconds: int = Field(default=30, alias="SENDER_NEXT_HEARTBEAT_SECONDS")

    # Collectors
    collector_request_timeout_seconds: int = Field(default=10, alias="COLLECTOR_REQUEST_TIMEOUT_SECONDS")
    collector_user_agent: str = Field(default="finance-news-bot/0.1", alias="COLLECTOR_USER_AGENT")
    cls_base_url: str = Field(default="https://www.cls.cn/telegraph", alias="CLS_BASE_URL")
    baidu_hotsearch_url: str = Field(default="https://top.baidu.com/board?tab=realtime", alias="BAIDU_HOTSEARCH_URL")
    candidate_event_limit_per_section: int = Field(default=20, alias="CANDIDATE_EVENT_LIMIT_PER_SECTION")

    # LLM
    llm_enabled: bool = Field(default=False, alias="LLM_ENABLED")
    llm_api_url: str | None = Field(default=None, alias="LLM_API_URL")
    llm_api_key: str | None = Field(default=None, alias="LLM_API_KEY")
    llm_model: str | None = Field(default=None, alias="LLM_MODEL")
    llm_timeout_seconds: int = Field(default=20, alias="LLM_TIMEOUT_SECONDS")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @property
    def database_url(self) -> str:
        if self.database_url_override:
            return self.database_url_override
        return (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def redis_url(self) -> str:
        if self.redis_url_override:
            return self.redis_url_override
        credentials = ""
        if self.redis_password:
            credentials = f":{self.redis_password}@"
        return f"redis://{credentials}{self.redis_host}:{self.redis_port}/{self.redis_db}"

    @property
    def effective_scheduler_timezone(self) -> str:
        return self.scheduler_timezone or self.timezone


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
