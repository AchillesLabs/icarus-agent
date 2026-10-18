"""Domain schemas, DTOs, and enums for sessions, messages, and agent runs."""

import json
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


class SessionSummaryDTO(BaseModel):
    """High-level session metadata and aggregated telemetry."""

    id: str
    owner_id: str = "default"
    mode: str = "chat"
    title: str = "New Session"
    created_at: datetime
    updated_at: datetime
    message_count: int = 0
    run_count: int = 0
    total_estimated_tokens: int = 0


class SessionResponse(BaseModel):
    """API response model for detailed session information and metrics."""

    id: str
    owner_id: str = "default"
    mode: str = "chat"
    title: str = "New Session"
    created_at: datetime
    updated_at: datetime
    metadata_version: int = 1
    message_count: int = 0
    run_count: int = 0
    total_estimated_tokens: int = 0


class SessionListResponse(BaseModel):
    """API response model for paginated session summaries."""

    items: list[SessionSummaryDTO]
    total: int
    limit: int
    offset: int


class MessageResponse(BaseModel):
    """API response model for an individual transcript message."""

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


class SessionCreateRequest(BaseModel):
    """API request payload to initiate a new session."""

    title: str = "New Session"
    mode: str = "chat"


class MessageCreateRequest(BaseModel):
    """API request payload to append a message to a session."""

    content: str
    role: MessageRole | str = MessageRole.USER
    tool_calls: list[Any] | None = None
    tool_call_id: str | None = None
    name: str | None = None


class SSEEventType(StrEnum):
    """Event types emitted during Server-Sent Events (SSE) agent run streaming."""

    TURN_START = "turn_start"
    TOKEN = "token"
    TOOL_START = "tool_start"
    TOOL_END = "tool_end"
    COMPACTION = "compaction"
    RUN_COMPLETED = "run_completed"
    RUN_CANCELLED = "run_cancelled"
    RUN_FAILED = "run_failed"


class SSEEventPayload(BaseModel):
    """Payload envelope for real-time Server-Sent Events streamed during an agent run."""

    event: SSEEventType | str
    data: dict[str, Any] = Field(default_factory=dict)
    id: str | None = None
    retry: int | None = None

    def to_sse_message(self) -> str:
        """Format as an RFC-compliant Server-Sent Event string."""
        event_str = self.event.value if hasattr(self.event, "value") else str(self.event)
        data_json = json.dumps(self.data)
        lines: list[str] = []
        if self.id is not None:
            lines.append(f"id: {self.id}")
        lines.append(f"event: {event_str}")
        lines.append(f"data: {data_json}")
        if self.retry is not None:
            lines.append(f"retry: {self.retry}")
        return "\n".join(lines) + "\n\n"

    @classmethod
    def turn_start(cls, turn: int, run_id: str | None = None) -> "SSEEventPayload":
        return cls(event=SSEEventType.TURN_START, data={"turn": turn, "run_id": run_id})

    @classmethod
    def token(cls, delta: str, run_id: str | None = None) -> "SSEEventPayload":
        return cls(event=SSEEventType.TOKEN, data={"delta": delta, "run_id": run_id})

    @classmethod
    def tool_start(
        cls,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
        tool_call_id: str | None = None,
        run_id: str | None = None,
    ) -> "SSEEventPayload":
        return cls(
            event=SSEEventType.TOOL_START,
            data={
                "tool_name": tool_name,
                "arguments": arguments or {},
                "tool_call_id": tool_call_id,
                "run_id": run_id,
            },
        )

    @classmethod
    def tool_end(
        cls,
        tool_name: str,
        output: str = "",
        error: str | None = None,
        tool_call_id: str | None = None,
        run_id: str | None = None,
    ) -> "SSEEventPayload":
        return cls(
            event=SSEEventType.TOOL_END,
            data={
                "tool_name": tool_name,
                "output": output,
                "error": error,
                "tool_call_id": tool_call_id,
                "run_id": run_id,
            },
        )

    @classmethod
    def compaction(
        cls,
        tokens_saved: int,
        original_message_count: int,
        compacted_message_count: int,
        run_id: str | None = None,
    ) -> "SSEEventPayload":
        return cls(
            event=SSEEventType.COMPACTION,
            data={
                "tokens_saved": tokens_saved,
                "original_message_count": original_message_count,
                "compacted_message_count": compacted_message_count,
                "run_id": run_id,
            },
        )

    @classmethod
    def run_completed(
        cls,
        run_id: str,
        result: str = "",
        budget_counters: dict[str, Any] | None = None,
    ) -> "SSEEventPayload":
        return cls(
            event=SSEEventType.RUN_COMPLETED,
            data={
                "run_id": run_id,
                "status": "succeeded",
                "result": result,
                "budget_counters": budget_counters or {},
            },
        )

    @classmethod
    def run_cancelled(
        cls,
        run_id: str,
        message: str = "Run was cancelled",
        budget_counters: dict[str, Any] | None = None,
    ) -> "SSEEventPayload":
        return cls(
            event=SSEEventType.RUN_CANCELLED,
            data={
                "run_id": run_id,
                "status": "cancelled",
                "message": message,
                "budget_counters": budget_counters or {},
            },
        )

    @classmethod
    def run_failed(
        cls,
        run_id: str,
        error: str,
        error_category: str | None = None,
    ) -> "SSEEventPayload":
        return cls(
            event=SSEEventType.RUN_FAILED,
            data={
                "run_id": run_id,
                "status": "failed",
                "error": error,
                "error_category": error_category,
            },
        )


class RunCreateRequest(BaseModel):
    """Payload to initiate an execution run on a session."""

    prompt: str | None = None
    model: str | None = None
    provider: str | None = None
    temperature: float | None = None
    max_turns: int | None = None
    max_total_tokens: int | None = None
    auto_compact: bool = True
    auto_approve: bool = True


class RunResponse(BaseModel):
    """API response model for detailed agent run state and metrics."""

    id: str
    owner_id: str = "default"
    session_id: str | None = None
    status: RunStatus | str = RunStatus.QUEUED
    provider: str | None = None
    model: str | None = None
    budget_counters: dict[str, Any] | None = None
    error_category: str | None = None
    idempotency_key: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None


class RunCancelResponse(BaseModel):
    """API response model when cancelling an active or queued run."""

    run_id: str
    status: RunStatus | str
    cancelled: bool
    message: str | None = None
