"""Configuration settings for Icarus API server."""

from pydantic import Field
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
