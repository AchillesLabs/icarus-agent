"""Tests for ModelProvider protocol, provider DTOs, and exception hierarchy."""

from collections.abc import AsyncIterator

from icarus_contracts import (
    AuthenticationError,
    CompletionResult,
    ContextLengthExceededError,
    MessageRole,
    PromptMessage,
    ProviderCapabilities,
    ProviderError,
    ProviderUnavailableError,
    RateLimitError,
    StreamChunk,
)
from icarus_core.providers.base import ModelProvider


def test_provider_exceptions_inherit_from_provider_error():
    assert issubclass(AuthenticationError, ProviderError)
    assert issubclass(RateLimitError, ProviderError)
    assert issubclass(ContextLengthExceededError, ProviderError)
    assert issubclass(ProviderUnavailableError, ProviderError)
    assert issubclass(ProviderError, Exception)


def test_prompt_message_dto():
    msg = PromptMessage(role=MessageRole.USER, content="Hello")
    assert msg.role == MessageRole.USER
    assert msg.content == "Hello"
    assert msg.name is None


def test_stream_chunk_dto():
    chunk = StreamChunk(delta="world", finish_reason=None)
    assert chunk.delta == "world"
    assert chunk.finish_reason is None

    final_chunk = StreamChunk(delta="", finish_reason="stop", usage={"total_tokens": 42})
    assert final_chunk.finish_reason == "stop"
    assert final_chunk.usage == {"total_tokens": 42}


def test_completion_result_dto():
    result = CompletionResult(content="Complete response", model="grok-2", finish_reason="stop")
    assert result.content == "Complete response"
    assert result.model == "grok-2"
    assert result.finish_reason == "stop"


def test_provider_capabilities_dto():
    caps = ProviderCapabilities(
        supported_models=["grok-2", "grok-beta"],
        max_context_tokens=131072,
        supports_streaming=True,
    )
    assert "grok-2" in caps.supported_models
    assert caps.max_context_tokens == 131072
    assert caps.supports_streaming is True


def test_model_provider_runtime_protocol():
    class DummyProvider:
        async def generate(
            self,
            messages: list[PromptMessage],
            model: str | None = None,
            temperature: float = 0.7,
            max_tokens: int | None = None,
        ) -> CompletionResult:
            return CompletionResult(content="ok", model="dummy")

        async def stream(
            self,
            messages: list[PromptMessage],
            model: str | None = None,
            temperature: float = 0.7,
            max_tokens: int | None = None,
        ) -> AsyncIterator[StreamChunk]:
            yield StreamChunk(delta="ok")

        def get_capabilities(self, model: str | None = None) -> ProviderCapabilities:
            return ProviderCapabilities(supported_models=["dummy"], max_context_tokens=4096)

    dummy = DummyProvider()
    assert isinstance(dummy, ModelProvider)
