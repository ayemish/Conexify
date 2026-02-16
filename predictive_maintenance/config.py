"""
PDM Configuration Management

Centralized configuration using Pydantic settings with environment variable support.
"""

import os
from typing import List, Optional
from functools import lru_cache
from pydantic import AliasChoices, Field, validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Load .env early so nested BaseSettings classes see values even when the
# app is imported outside the CLI entrypoint.
try:
    from dotenv import load_dotenv
    _env_path = os.path.join(os.path.dirname(__file__), ".env")
    if os.path.exists(_env_path):
        load_dotenv(_env_path)
except Exception:
    pass


class DatabaseSettings(BaseSettings):
    """Database configuration — PostgreSQL with SQLite fallback for dev"""
    host: str = Field(default="localhost", env="PDM_DB_HOST")
    port: int = Field(default=5432, env="PDM_DB_PORT")
    name: str = Field(default="pdm", env="PDM_DB_NAME")
    user: str = Field(default="pdm_user", env="PDM_DB_USER")
    password: str = Field(default="", env="PDM_DB_PASSWORD")
    pool_size: int = Field(default=5, env="PDM_DB_POOL_SIZE")
    max_overflow: int = Field(default=10, env="PDM_DB_MAX_OVERFLOW")
    sqlite_path: str = Field(default="pdm_dev.db", env="PDM_DB_SQLITE_PATH")
    use_sqlite: Optional[bool] = Field(default=None, env="PDM_DB_USE_SQLITE")
    
    @property
    def _should_use_sqlite(self) -> bool:
        """Auto-detect: use SQLite if explicitly requested or PostgreSQL unavailable."""
        if self.use_sqlite is True:
            return True
        if self.use_sqlite is False:
            return False
        # Auto-detect: try PostgreSQL, fall back to SQLite
        try:
            import socket
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(1)
            s.connect((self.host, self.port))
            s.close()
            return False
        except (OSError, ConnectionRefusedError):
            return True

    @property
    def url(self) -> str:
        """Build database URL — PostgreSQL or SQLite fallback"""
        if self._should_use_sqlite:
            return f"sqlite:///{self.sqlite_path}"
        return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.name}"
    
    @property
    def async_url(self) -> str:
        """Build async database URL"""
        if self._should_use_sqlite:
            return f"sqlite+aiosqlite:///{self.sqlite_path}"
        return f"postgresql+asyncpg://{self.user}:{self.password}@{self.host}:{self.port}/{self.name}"
    
    model_config = SettingsConfigDict(
        env_prefix="PDM_DB_",
        extra="ignore",
        case_sensitive=False,
    )


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
    
    model_config = SettingsConfigDict(
        env_prefix="PDM_REDIS_",
        extra="ignore",
        case_sensitive=False,
    )


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
    
    model_config = SettingsConfigDict(
        env_prefix="PDM_API_",
        extra="ignore",
        case_sensitive=False,
    )


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
    max_actionable_alarms_per_fleet_per_month: Optional[float] = Field(
        default=None, env="PDM_FP_MAX_ALARMS_PER_FLEET"
    )
    
    model_config = SettingsConfigDict(
        env_prefix="PDM_FP_",
        extra="ignore",
        case_sensitive=False,
    )


class ChangeDetectionSettings(BaseSettings):
    """Change detection algorithm defaults"""
    cusum_threshold: float = Field(default=5.0, env="PDM_CD_CUSUM_THRESHOLD")
    cusum_slack: float = Field(default=0.5, env="PDM_CD_CUSUM_SLACK")
    glr_threshold: float = Field(default=10.0, env="PDM_CD_GLR_THRESHOLD")
    min_persistence_minutes: float = Field(default=360.0, env="PDM_CD_MIN_PERSISTENCE")
    min_steady_state_regimes: int = Field(default=2, env="PDM_CD_MIN_REGIMES")
    stability_window: int = Field(default=50, env="PDM_CD_STABILITY_WINDOW")
    
    model_config = SettingsConfigDict(
        env_prefix="PDM_CD_",
        extra="ignore",
        case_sensitive=False,
    )


class LoggingSettings(BaseSettings):
    """Logging configuration"""
    level: str = Field(default="INFO", env="PDM_LOG_LEVEL")
    format: str = Field(default="json", env="PDM_LOG_FORMAT")  # json or text
    include_trace_id: bool = Field(default=True, env="PDM_LOG_TRACE_ID")
    
    model_config = SettingsConfigDict(
        env_prefix="PDM_LOG_",
        extra="ignore",
        case_sensitive=False,
    )


class MetricsSettings(BaseSettings):
    """Metrics and observability configuration"""
    enabled: bool = Field(default=True, env="PDM_METRICS_ENABLED")
    port: int = Field(default=9090, env="PDM_METRICS_PORT")
    prefix: str = Field(default="pdm", env="PDM_METRICS_PREFIX")
    
    # Tracing
    tracing_enabled: bool = Field(default=False, env="PDM_TRACING_ENABLED")
    jaeger_host: str = Field(default="localhost", env="PDM_JAEGER_HOST")
    jaeger_port: int = Field(default=6831, env="PDM_JAEGER_PORT")
    
    model_config = SettingsConfigDict(
        env_prefix="PDM_METRICS_",
        extra="ignore",
        case_sensitive=False,
    )


class OpenAISettings(BaseSettings):
    """OpenAI integration settings"""
    api_key: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices(
            "OPENAI_API_KEY",
            "openai_api_key",
            "PDM_OPENAI_API_KEY",
        ),
    )
    embedding_model: str = Field(default="text-embedding-3-small", env="PDM_OPENAI_EMBEDDING_MODEL")
    chat_model: str = Field(
        default="gpt-4o-mini",
        validation_alias=AliasChoices(
            "PDM_OPENAI_CHAT_MODEL",
            "OPENAI_MODEL",
            "openai_model",
        ),
    )
    transcription_model: str = Field(default="whisper-1", env="PDM_OPENAI_TRANSCRIBE_MODEL")
    max_context_docs: int = Field(default=6, env="PDM_OPENAI_MAX_CONTEXT_DOCS")
    scenario_crewai_enabled: bool = Field(default=False, env="PDM_OPENAI_SCENARIO_CREWAI_ENABLED")
    
    model_config = SettingsConfigDict(
        env_prefix="PDM_OPENAI_",
        extra="ignore",
        case_sensitive=False,
    )


class TEESettings(BaseSettings):
    """TEE / Release Gate integration settings"""
    enabled: bool = Field(default=False, env="TEE_ENABLED")
    release_gate_url: str = Field(default="http://vcda-release-gate:8080", env="TEE_RELEASE_GATE_URL")
    release_policy_name: Optional[str] = Field(default=None, env="TEE_RELEASE_POLICY_NAME")
    release_policy_namespace: Optional[str] = Field(default=None, env="TEE_RELEASE_POLICY_NAMESPACE")
    dataset_binding_name: Optional[str] = Field(default=None, env="TEE_DATASET_BINDING_NAME")
    dataset_binding_namespace: Optional[str] = Field(default=None, env="TEE_DATASET_BINDING_NAMESPACE")

    # Attestation / Keylime
    keylime_enabled: bool = Field(default=False, env="TEE_KEYLIME_ENABLED")
    keylime_verifier_url: str = Field(default="http://keylime-verifier:8881", env="TEE_KEYLIME_VERIFIER_URL")
    keylime_fail_closed: bool = Field(default=True, env="TEE_KEYLIME_FAIL_CLOSED")
    keylime_required_ima_policy_hashes: Optional[str] = Field(default=None, env="TEE_KEYLIME_REQUIRED_IMA_HASHES")

    # Enclave runtime / IO
    enclave_runtime: str = Field(default="kata", env="TEE_ENCLAVE_RUNTIME")
    egress_allowlist: List[str] = Field(default_factory=list, env="TEE_EGRESS_ALLOWLIST")
    encryption_key: Optional[str] = Field(default=None, env="TEE_ENCRYPTION_KEY")

    model_config = SettingsConfigDict(
        env_prefix="TEE_",
        extra="ignore",
        case_sensitive=False,
    )


class PersistenceSettings(BaseSettings):
    """Persistence feature flags"""
    enabled: bool = Field(default=False, env="PDM_PERSISTENCE_ENABLED")

    model_config = SettingsConfigDict(
        env_prefix="PDM_PERSISTENCE_",
        extra="ignore",
        case_sensitive=False,
    )


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
    openai: OpenAISettings = Field(default_factory=OpenAISettings)
    persistence: PersistenceSettings = Field(default_factory=PersistenceSettings)
    tee: TEESettings = Field(default_factory=TEESettings)
    
    @property
    def is_production(self) -> bool:
        return self.environment == "production"
    
    @property
    def is_development(self) -> bool:
        return self.environment == "development"
    
    model_config = SettingsConfigDict(
        env_prefix="PDM_",
        # Always resolve .env relative to this package, not process CWD.
        env_file=os.path.join(os.path.dirname(__file__), ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache()
def get_settings() -> PDMSettings:
    """Get cached settings instance"""
    return PDMSettings()


# Convenience accessor
settings = get_settings()
