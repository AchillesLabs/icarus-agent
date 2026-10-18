"""Domain contracts and Pydantic schemas for scheduled jobs and background tasks."""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class ScheduledJobStatus(StrEnum):
    """Execution status for a scheduled background job."""

    PENDING = "pending"
    CLAIMED = "claimed"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ScheduledJobCreate(BaseModel):
    """Payload to register a new scheduled job or reminder."""

    job_type: str = Field(..., min_length=1, max_length=64, description="Job category or task name")
    scheduled_at: datetime = Field(
        ..., description="Timestamp when the job becomes eligible for execution"
    )
    payload: dict[str, Any] | None = Field(
        default=None, description="Arbitrary task execution arguments"
    )
    owner_id: str | None = Field(default=None, description="Tenant/owner identifier")


class ScheduledJobUpdate(BaseModel):
    """Payload to mutate mutable fields on an existing scheduled job."""

    status: ScheduledJobStatus | str | None = None
    payload: dict[str, Any] | None = None
    claimed_by: str | None = None
    claimed_at: datetime | None = None
    completed_at: datetime | None = None
    error_message: str | None = None
    retry_count: int | None = None
    scheduled_at: datetime | None = None


class ScheduledJobDTO(BaseModel):
    """Immutable data transfer object representing a persistent scheduled job."""

    id: str
    owner_id: str
    job_type: str
    scheduled_at: datetime
    status: ScheduledJobStatus
    payload: dict[str, Any] | None = None
    claimed_by: str | None = None
    claimed_at: datetime | None = None
    completed_at: datetime | None = None
    error_message: str | None = None
    retry_count: int = 0
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
