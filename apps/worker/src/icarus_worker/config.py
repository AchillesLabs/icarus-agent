"""Runtime configuration for the background worker daemon."""

import uuid

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class WorkerSettings(BaseSettings):
    """Configuration for autonomous background worker and task scheduler."""

    model_config = SettingsConfigDict(
        env_prefix="ICARUS_WORKER_",
        extra="ignore",
    )

    worker_id: str = Field(default_factory=lambda: f"worker-{uuid.uuid4().hex[:8]}")
    poll_interval_seconds: float = 1.0
    poll_max_backoff_seconds: float = 10.0
    lease_duration_seconds: int = 300
    database_url: str | None = None
    max_retries: int = 3
    retry_backoff_base_seconds: int = 60
    default_provider: str = "mock"
    default_model: str = "mock-model"


WorkerConfig = WorkerSettings
