"""
PDM Configuration Management

Centralized configuration using Pydantic settings with environment variable support.
"""

import os
from typing import List, Optional
from functools import lru_cache
from pydantic import BaseSettings, Field, validator


class DatabaseSettings(BaseSettings):
    """Database configuration"""
    host: str = Field(default="localhost", env="PDM_DB_HOST")
    port: int = Field(default=5432, env="PDM_DB_PORT")
    name: str = Field(default="pdm", env="PDM_DB_NAME")
    user: str = Field(default="pdm_user", env="PDM_DB_USER")
    password: str = Field(default="", env="PDM_DB_PASSWORD")
    pool_size: int = Field(default=5, env="PDM_DB_POOL_SIZE")
    max_overflow: int = Field(default=10, env="PDM_DB_MAX_OVERFLOW")
    
    @property
    def url(self) -> str:
        """Build database URL"""
        return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.name}"
    
    @property
    def async_url(self) -> str:
        """Build async database URL"""
        return f"postgresql+asyncpg://{self.user}:{self.password}@{self.host}:{self.port}/{self.name}"
    
    class Config:
        env_prefix = "PDM_DB_"


class RedisSettings(BaseSettings):
    """Redis configuration"""
    host: str = Field(default="localhost", env="PDM_REDIS_HOST")
    port: int = Field(default=6379, env="PDM_REDIS_PORT")
    password: Optional[str] = Field(default=None, env="PDM_REDIS_PASSWORD")
    db: int = Field(default=0, env="PDM_REDIS_DB")
    ssl: bool = Field(default=False, env="PDM_REDIS_SSL")
    
    # Event bus settings
    event_ttl_seconds: int = Field(default=86400, env="PDM_REDIS_EVENT_TTL")
    dead_letter_ttl_seconds: int = Field(default=604800, env="PDM_REDIS_DLQ_TTL")
    
    @property
    def url(self) -> str:
        """Build Redis URL"""
        protocol = "rediss" if self.ssl else "redis"
        auth = f":{self.password}@" if self.password else ""
        return f"{protocol}://{auth}{self.host}:{self.port}/{self.db}"
    
    class Config:
        env_prefix = "PDM_REDIS_"


class APISettings(BaseSettings):
    """API server configuration"""
    host: str = Field(default="0.0.0.0", env="PDM_API_HOST")
    port: int = Field(default=8000, env="PDM_API_PORT")
    workers: int = Field(default=4, env="PDM_API_WORKERS")
    reload: bool = Field(default=False, env="PDM_API_RELOAD")
    
    # Security
    api_key_header: str = Field(default="X-API-Key", env="PDM_API_KEY_HEADER")
    api_keys: List[str] = Field(default_factory=list, env="PDM_API_KEYS")
    cors_origins: List[str] = Field(default=["*"], env="PDM_CORS_ORIGINS")
    
    # Rate limiting
    rate_limit_requests: int = Field(default=100, env="PDM_RATE_LIMIT_REQUESTS")
    rate_limit_window_seconds: int = Field(default=60, env="PDM_RATE_LIMIT_WINDOW")
    
    @validator("api_keys", pre=True)
    def split_api_keys(cls, v):
        if isinstance(v, str):
            return [k.strip() for k in v.split(",") if k.strip()]
        return v
    
    @validator("cors_origins", pre=True)
    def split_cors_origins(cls, v):
        if isinstance(v, str):
            return [o.strip() for o in v.split(",") if o.strip()]
        return v
    
    class Config:
        env_prefix = "PDM_API_"


class FalsePositiveBudgetSettings(BaseSettings):
    """False positive budget defaults"""
    max_actionable_alarms_per_unit_per_month: float = Field(
        default=0.3, env="PDM_FP_MAX_ALARMS_PER_MONTH"
    )
    max_no_issue_found_rate: float = Field(
        default=0.05, env="PDM_FP_MAX_NIF_RATE"
    )
    min_confidence_for_actionable: float = Field(
        default=0.85, env="PDM_FP_MIN_CONFIDENCE"
    )
    max_false_alarm_probability: float = Field(
        default=0.02, env="PDM_FP_MAX_FA_PROB"
    )
    min_anomaly_persistence_hours: float = Field(
        default=6.0, env="PDM_FP_MIN_PERSISTENCE_HOURS"
    )
    min_regime_coverage_cycles: int = Field(
        default=2, env="PDM_FP_MIN_REGIME_CYCLES"
    )
    
    class Config:
        env_prefix = "PDM_FP_"


class ChangeDetectionSettings(BaseSettings):
    """Change detection algorithm defaults"""
    cusum_threshold: float = Field(default=5.0, env="PDM_CD_CUSUM_THRESHOLD")
    cusum_slack: float = Field(default=0.5, env="PDM_CD_CUSUM_SLACK")
    glr_threshold: float = Field(default=10.0, env="PDM_CD_GLR_THRESHOLD")
    min_persistence_minutes: float = Field(default=360.0, env="PDM_CD_MIN_PERSISTENCE")
    min_steady_state_regimes: int = Field(default=2, env="PDM_CD_MIN_REGIMES")
    stability_window: int = Field(default=50, env="PDM_CD_STABILITY_WINDOW")
    
    class Config:
        env_prefix = "PDM_CD_"


class LoggingSettings(BaseSettings):
    """Logging configuration"""
    level: str = Field(default="INFO", env="PDM_LOG_LEVEL")
    format: str = Field(default="json", env="PDM_LOG_FORMAT")  # json or text
    include_trace_id: bool = Field(default=True, env="PDM_LOG_TRACE_ID")
    
    class Config:
        env_prefix = "PDM_LOG_"


class MetricsSettings(BaseSettings):
    """Metrics and observability configuration"""
    enabled: bool = Field(default=True, env="PDM_METRICS_ENABLED")
    port: int = Field(default=9090, env="PDM_METRICS_PORT")
    prefix: str = Field(default="pdm", env="PDM_METRICS_PREFIX")
    
    # Tracing
    tracing_enabled: bool = Field(default=False, env="PDM_TRACING_ENABLED")
    jaeger_host: str = Field(default="localhost", env="PDM_JAEGER_HOST")
    jaeger_port: int = Field(default=6831, env="PDM_JAEGER_PORT")
    
    class Config:
        env_prefix = "PDM_METRICS_"


class PDMSettings(BaseSettings):
    """Main PDM application settings"""
    environment: str = Field(default="development", env="PDM_ENVIRONMENT")
    debug: bool = Field(default=False, env="PDM_DEBUG")
    site_id: str = Field(default="default", env="PDM_SITE_ID")
    
    # Sub-configurations
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    api: APISettings = Field(default_factory=APISettings)
    false_positive_budget: FalsePositiveBudgetSettings = Field(
        default_factory=FalsePositiveBudgetSettings
    )
    change_detection: ChangeDetectionSettings = Field(
        default_factory=ChangeDetectionSettings
    )
    logging: LoggingSettings = Field(default_factory=LoggingSettings)
    metrics: MetricsSettings = Field(default_factory=MetricsSettings)
    
    @property
    def is_production(self) -> bool:
        return self.environment == "production"
    
    @property
    def is_development(self) -> bool:
        return self.environment == "development"
    
    class Config:
        env_prefix = "PDM_"
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


@lru_cache()
def get_settings() -> PDMSettings:
    """Get cached settings instance"""
    return PDMSettings()


# Convenience accessor
settings = get_settings()
