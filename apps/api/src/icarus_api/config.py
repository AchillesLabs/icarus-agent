import json
from typing import Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ApiSettings(BaseSettings):
    """Runtime configuration for the FastAPI service."""

    model_config = SettingsConfigDict(
        env_prefix="ICARUS_API_",
        extra="ignore",
    )

    title: str = "Icarus Agent API"
    version: str = "0.1.0"
    description: str = "Remote execution and streaming API service for Icarus Agent"
    host: str = "127.0.0.1"
    port: int = 8000
    cors_origins: list[str] = Field(default_factory=lambda: ["*"])
    database_url: str | None = None
    auth_token: str | None = None
    auth_tokens: dict[str, str] = Field(default_factory=dict)
    default_owner_id: str = "default"
    default_provider: str = "mock"
    default_model: str = "mock-model"
    allow_fallback_to_system_credentials: bool = True
    rate_limit_enabled: bool = True
    rate_limit_rpm: int = 60
    rate_limit_window_seconds: float = 60.0
    max_concurrent_runs_per_tenant: int = 5

    @field_validator("auth_tokens", mode="before")
    @classmethod
    def _parse_auth_tokens(cls, v: Any) -> dict[str, str]:
        if isinstance(v, dict):
            return {str(k): str(val) for k, val in v.items()}
        if isinstance(v, str):
            v = v.strip()
            if not v:
                return {}
            if v.startswith("{"):
                try:
                    parsed = json.loads(v)
                    if isinstance(parsed, dict):
                        return {str(k): str(val) for k, val in parsed.items()}
                except json.JSONDecodeError:
                    pass
            # Try comma-delimited token:owner pairs
            mapping: dict[str, str] = {}
            for item in v.split(","):
                item = item.strip()
                if not item:
                    continue
                if ":" in item:
                    tok, _, owner = item.partition(":")
                    if tok.strip() and owner.strip():
                        mapping[tok.strip()] = owner.strip()
            return mapping
        return {}
