"""Application configuration loaded from environment variables."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """SentinelFlow runtime settings.

    Connection strings are secret values so accidental model serialization and log
    formatting cannot expose embedded credentials.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="SENTINELFLOW_",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "SentinelFlow"
    environment: Literal["development", "test", "production"] = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    api_prefix: str = "/api/v1"
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])

    database_url: SecretStr = SecretStr(
        "postgresql+asyncpg://sentinelflow:sentinelflow@localhost:5432/sentinelflow"
    )
    redis_url: SecretStr = SecretStr("redis://localhost:6379/0")
    dependency_timeout_seconds: float = Field(default=2.0, gt=0, le=30)

    otel_enabled: bool = False
    otel_service_name: str = "sentinelflow-api"
    otel_exporter_otlp_endpoint: str = "http://localhost:4317"

    @field_validator("api_prefix")
    @classmethod
    def validate_api_prefix(cls, value: str) -> str:
        """Require an absolute API prefix and normalize its trailing slash."""
        if not value.startswith("/"):
            raise ValueError("api_prefix must start with '/'")
        return value.rstrip("/") or "/"


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide immutable configuration instance."""
    return Settings()
