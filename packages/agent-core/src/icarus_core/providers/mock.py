"""Deterministic MockProvider for fast offline testing."""

import asyncio
from collections.abc import AsyncIterator

from icarus_contracts.provider import (
    CompletionResult,
    PromptMessage,
    ProviderCapabilities,
    StreamChunk,
)


class MockProvider:
    """Mock LLM provider simulating completions and streaming token deltas.

    Does not consume API credits.
    """

    def __init__(
        self,
        responses: list[str] | None = None,
        canned_chunks: list[str] | None = None,
        should_fail: Exception | None = None,
        latency: float = 0.0,
    ) -> None:
        self.responses = (
            list(responses) if responses is not None else ["Mock response from Icarus agent."]
        )
        self.canned_chunks = list(canned_chunks) if canned_chunks is not None else None
        self.should_fail = should_fail
        self.latency = latency

        self.call_count: int = 0
        self.recorded_prompts: list[list[PromptMessage]] = []
        self.recorded_models: list[str] = []
        self._response_index: int = 0

    def _get_next_response(self) -> str:
        if not self.responses:
            return "Default mock completion."
        response = self.responses[self._response_index % len(self.responses)]
        self._response_index += 1
        return response

    async def generate(
        self,
        messages: list[PromptMessage],
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> CompletionResult:
        """Return a simulated completion."""
        self.call_count += 1
        self.recorded_prompts.append(messages)
        target_model = model or "mock-model"
        self.recorded_models.append(target_model)

        if self.should_fail is not None:
            raise self.should_fail

        if self.latency > 0:
            await asyncio.sleep(self.latency)

        text = self._get_next_response()
        word_count = len(text.split())
        return CompletionResult(
            content=text,
            model=target_model,
            finish_reason="stop",
            usage={
                "prompt_tokens": 10,
                "completion_tokens": word_count,
                "total_tokens": 10 + word_count,
            },
        )

    async def stream(
        self,
        messages: list[PromptMessage],
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> AsyncIterator[StreamChunk]:
        """Stream simulated token deltas asynchronously."""
        self.call_count += 1
        self.recorded_prompts.append(messages)
        target_model = model or "mock-model"
        self.recorded_models.append(target_model)

        if self.should_fail is not None:
            raise self.should_fail

        if self.canned_chunks is not None:
            chunks = list(self.canned_chunks)
        else:
            text = self._get_next_response()
            # Split into word pieces with spacing preserved
            words = text.split(" ")
            chunks = [w + " " for w in words[:-1]] + ([words[-1]] if words else [])

        for chunk_text in chunks:
            if self.latency > 0:
                await asyncio.sleep(self.latency)
            yield StreamChunk(delta=chunk_text)

        yield StreamChunk(
            delta="",
            finish_reason="stop",
            usage={
                "prompt_tokens": 10,
                "completion_tokens": len(chunks),
                "total_tokens": 10 + len(chunks),
            },
        )

    def get_capabilities(self, model: str | None = None) -> ProviderCapabilities:
        """Advertise mock capabilities."""
        return ProviderCapabilities(
            supported_models=["mock-model", "mock-fast"],
            max_context_tokens=128000,
            supports_streaming=True,
            supports_tools=True,
            supports_vision=True,
        )
