"""Domain schemas, DTOs, and enums for sessions, messages, and agent runs."""

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class MessageRole(StrEnum):
    """Role associated with a message in a conversation thread."""

    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


class RunStatus(StrEnum):
    """Lifecycle status of an agent run."""

    QUEUED = "queued"
    RUNNING = "running"
    WAITING_FOR_APPROVAL = "waiting_for_approval"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class SessionCreate(BaseModel):
    """Input payload to create a new session."""

    title: str = "New Session"
    mode: str = "chat"
    owner_id: str = "default"


class SessionUpdate(BaseModel):
    """Input payload to update an existing session."""

    title: str | None = None
    mode: str | None = None
    metadata_version: int | None = None


class SessionDTO(BaseModel):
    """Persisted session data transfer object."""

    id: str
    owner_id: str = "default"
    mode: str = "chat"
    title: str = "New Session"
    created_at: datetime
    updated_at: datetime
    metadata_version: int = 1


class MessageCreate(BaseModel):
    """Input payload to append a message to a session."""

    session_id: str
    role: MessageRole | str
    content: str | None = ""
    owner_id: str = "default"
    token_estimate: int | None = None
    tool_calls: list[Any] | None = None
    tool_call_id: str | None = None
    name: str | None = None


class MessageDTO(BaseModel):
    """Persisted message data transfer object."""

    id: str
    session_id: str
    owner_id: str = "default"
    role: MessageRole | str
    content: str | None = ""
    token_estimate: int | None = None
    created_at: datetime
    tool_calls: list[dict[str, Any]] | None = None
    tool_call_id: str | None = None
    name: str | None = None

    def to_prompt_message(self) -> Any:
        """Convert persisted message DTO into a PromptMessage for model execution."""
        from icarus_contracts.provider import PromptMessage
        from icarus_contracts.tools import ToolCall

        tcs: list[ToolCall] | None = None
        if self.tool_calls:
            tcs = [
                tc if isinstance(tc, ToolCall) else ToolCall.model_validate(tc)
                for tc in self.tool_calls
            ]
        return PromptMessage(
            role=self.role,
            content=self.content or "",
            name=self.name,
            tool_call_id=self.tool_call_id,
            tool_calls=tcs,
        )


class RunCreate(BaseModel):
    """Input payload to register a new agent run."""

    session_id: str | None = None
    owner_id: str = "default"
    status: RunStatus = RunStatus.QUEUED
    provider: str | None = None
    model: str | None = None
    budget_counters: dict[str, Any] | None = None
    idempotency_key: str | None = None


class RunDTO(BaseModel):
    """Persisted agent run data transfer object."""

    id: str
    owner_id: str = "default"
    session_id: str | None = None
    status: RunStatus | str = RunStatus.QUEUED
    provider: str | None = None
    model: str | None = None
    budget_counters: dict[str, Any] | None = Field(default=None)
    error_category: str | None = None
    idempotency_key: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
