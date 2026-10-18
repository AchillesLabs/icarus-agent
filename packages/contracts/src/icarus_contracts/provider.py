from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from icarus_contracts.session import MessageRole
from icarus_contracts.tools import ToolCall


class PromptMessage(BaseModel):
    """Normalized message input sent to a model provider."""

    role: MessageRole | str
    content: str | None = ""
    name: str | None = None
    tool_call_id: str | None = None
    tool_calls: list[ToolCall] | None = None


class StreamChunk(BaseModel):
    """Incremental delta event yielded during token streaming."""

    delta: str
    finish_reason: str | None = None
    usage: dict[str, Any] | None = None
    tool_calls: list[ToolCall] = Field(default_factory=list)
    tool_call_deltas: list[dict[str, Any]] | None = None


class CompletionResult(BaseModel):
    """Final output returned from a non-streaming or collected model generation."""

    content: str
    model: str
    finish_reason: str = "stop"
    usage: dict[str, Any] | None = None
    tool_calls: list[ToolCall] = Field(default_factory=list)


class ProviderCapabilities(BaseModel):
    """Capability metadata advertised by a model provider."""

    supported_models: list[str] = Field(default_factory=list)
    max_context_tokens: int = 128000
    supports_streaming: bool = True
    supports_tools: bool = False
    supports_vision: bool = False


class DiscoveredModel(BaseModel):
    """Metadata representing a model discovered from a provider's catalog."""

    id: str
    name: str
    provider: str
    context_window: int = 128000
    is_free: bool = False
    tier: str = "Paid"
    pricing_info: str = ""
    description: str = ""
