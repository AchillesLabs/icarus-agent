"""Contracts and schemas for model provider operations and streaming events."""

from typing import Any

from pydantic import BaseModel, Field

from icarus_contracts.session import MessageRole


class PromptMessage(BaseModel):
    """Normalized message input sent to a model provider."""

    role: MessageRole | str
    content: str
    name: str | None = None


class StreamChunk(BaseModel):
    """Incremental delta event yielded during token streaming."""

    delta: str
    finish_reason: str | None = None
    usage: dict[str, Any] | None = None


class CompletionResult(BaseModel):
    """Final output returned from a non-streaming or collected model generation."""

    content: str
    model: str
    finish_reason: str = "stop"
    usage: dict[str, Any] | None = None


class ProviderCapabilities(BaseModel):
    """Capability metadata advertised by a model provider."""

    supported_models: list[str] = Field(default_factory=list)
    max_context_tokens: int = 128000
    supports_streaming: bool = True
    supports_tools: bool = False
    supports_vision: bool = False
