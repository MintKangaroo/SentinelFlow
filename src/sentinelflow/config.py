"""Application configuration loaded from environment variables."""

from functools import lru_cache
from typing import Literal
from uuid import UUID

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
    workflow_execution_mode: Literal["dry_run", "external"] = "dry_run"
    workflow_dispatch_lease_seconds: int = Field(default=900, ge=30, le=3600)
    workflow_result_signing_key: SecretStr = SecretStr(
        "sentinelflow-local-result-signing-key-change-before-production"
    )
    integration_workspace_id: UUID | None = None
    aisoc_base_url: str | None = None
    aisoc_token: SecretStr | None = None
    aisoc_webhook_secret: SecretStr = SecretStr(
        "sentinelflow-local-aisoc-webhook-secret-change-before-production"
    )
    threatgraph_base_url: str | None = None
    threatgraph_token: SecretStr | None = None
    redmind_base_url: str | None = None
    redmind_token: SecretStr | None = None
    patchtower_base_url: str | None = None
    patchtower_token: SecretStr | None = None
    autopentest_base_url: str | None = None
    autopentest_token: SecretStr | None = None
    aishield_base_url: str | None = None
    aishield_token: SecretStr | None = None

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
