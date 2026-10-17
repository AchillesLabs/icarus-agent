"""Abstract base protocol for LLM model providers."""

from collections.abc import AsyncIterator
from typing import Any, Protocol, runtime_checkable

from icarus_contracts.provider import (
    CompletionResult,
    PromptMessage,
    ProviderCapabilities,
    StreamChunk,
)


@runtime_checkable
class ModelProvider(Protocol):
    """Protocol establishing standard async methods for model generation and streaming."""

    async def generate(
        self,
        messages: list[PromptMessage],
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        tools: list[dict[str, Any]] | None = None,
    ) -> CompletionResult:
        """Generate a complete non-streaming completion."""
        ...

    async def stream(
        self,
        messages: list[PromptMessage],
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[StreamChunk]:
        """Stream token deltas asynchronously as they arrive."""
        ...

    def get_capabilities(self, model: str | None = None) -> ProviderCapabilities:
        """Return provider and model capability limits."""
        ...
