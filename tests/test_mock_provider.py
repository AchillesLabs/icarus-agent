"""Tests for deterministic MockProvider."""

import pytest
from icarus_contracts import (
    MessageRole,
    PromptMessage,
    RateLimitError,
)
from icarus_core.providers.base import ModelProvider
from icarus_core.providers.mock import MockProvider


def test_mock_provider_conforms_to_protocol():
    provider = MockProvider()
    assert isinstance(provider, ModelProvider)


@pytest.mark.asyncio
async def test_mock_provider_generate():
    provider = MockProvider(responses=["Custom response 1", "Custom response 2"])
    messages = [PromptMessage(role=MessageRole.USER, content="Hello")]

    result1 = await provider.generate(messages, model="mock-model")
    assert result1.content == "Custom response 1"
    assert result1.model == "mock-model"
    assert provider.call_count == 1
    assert provider.recorded_prompts[0][0].content == "Hello"

    result2 = await provider.generate(messages)
    assert result2.content == "Custom response 2"
    assert provider.call_count == 2


@pytest.mark.asyncio
async def test_mock_provider_streaming():
    provider = MockProvider(canned_chunks=["Hello", " ", "world", "!"])
    messages = [PromptMessage(role=MessageRole.USER, content="Stream test")]

    chunks = []
    async for chunk in provider.stream(messages):
        chunks.append(chunk)

    deltas = [c.delta for c in chunks]
    assert "".join(deltas) == "Hello world!"
    # Last chunk has finish_reason
    assert chunks[-1].finish_reason == "stop"


@pytest.mark.asyncio
async def test_mock_provider_simulated_failure():
    err = RateLimitError("Simulated rate limit", provider="mock")
    provider = MockProvider(should_fail=err)
    messages = [PromptMessage(role=MessageRole.USER, content="Trigger fail")]

    with pytest.raises(RateLimitError) as exc_info:
        await provider.generate(messages)
    assert "rate limit" in str(exc_info.value).lower()

    with pytest.raises(RateLimitError):
        async for _ in provider.stream(messages):
            pass


def test_mock_provider_capabilities():
    provider = MockProvider()
    caps = provider.get_capabilities()
    assert "mock-model" in caps.supported_models
    assert caps.supports_streaming is True
