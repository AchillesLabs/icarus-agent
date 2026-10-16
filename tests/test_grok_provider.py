"""Tests for GrokProvider and xAI REST API error normalization."""

import json

import httpx
import pytest
from icarus_contracts import (
    AuthenticationError,
    ContextLengthExceededError,
    MessageRole,
    PromptMessage,
    ProviderUnavailableError,
    RateLimitError,
)
from icarus_core.providers.base import ModelProvider
from icarus_core.providers.grok import GrokProvider


def test_grok_provider_conforms_to_protocol():
    provider = GrokProvider(api_key="xai-test-key")
    assert isinstance(provider, ModelProvider)


@pytest.mark.asyncio
async def test_grok_provider_generate_success():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer xai-test-key"
        payload = json.loads(request.read())
        assert payload["model"] == "grok-2"
        assert payload["stream"] is False

        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-123",
                "choices": [
                    {
                        "message": {"role": "assistant", "content": "Hello from Grok!"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"total_tokens": 15},
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = GrokProvider(api_key="xai-test-key", client=client)

    result = await provider.generate([PromptMessage(role=MessageRole.USER, content="Hello")])
    assert result.content == "Hello from Grok!"
    assert result.model == "grok-2"
    assert result.finish_reason == "stop"


@pytest.mark.asyncio
async def test_grok_provider_stream_success():
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.read())
        assert payload["stream"] is True

        sse_body = (
            'data: {"choices":[{"delta":{"content":"Grok"},"finish_reason":null}]}\n\n'
            'data: {"choices":[{"delta":{"content":" response"},"finish_reason":null}]}\n\n'
            'data: {"choices":[{"delta":{"content":""},"finish_reason":"stop"}]}\n\n'
            "data: [DONE]\n\n"
        )
        return httpx.Response(
            200,
            text=sse_body,
            headers={"Content-Type": "text/event-stream"},
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = GrokProvider(api_key="xai-test-key", client=client)

    chunks = []
    async for chunk in provider.stream([PromptMessage(role=MessageRole.USER, content="Hello")]):
        chunks.append(chunk)

    deltas = [c.delta for c in chunks]
    assert "".join(deltas) == "Grok response"
    assert any(c.finish_reason == "stop" for c in chunks)


@pytest.mark.asyncio
async def test_grok_provider_normalizes_401_authentication_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"message": "Invalid API key"}})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = GrokProvider(api_key="bad-key", client=client)

    with pytest.raises(AuthenticationError):
        await provider.generate([PromptMessage(role=MessageRole.USER, content="Hello")])


@pytest.mark.asyncio
async def test_grok_provider_normalizes_429_rate_limit_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": {"message": "Rate limit exceeded"}})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = GrokProvider(api_key="xai-test-key", client=client)

    with pytest.raises(RateLimitError):
        await provider.generate([PromptMessage(role=MessageRole.USER, content="Hello")])


@pytest.mark.asyncio
async def test_grok_provider_normalizes_400_context_length_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": {"message": "Maximum context length exceeded"}})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = GrokProvider(api_key="xai-test-key", client=client)

    with pytest.raises(ContextLengthExceededError):
        await provider.generate([PromptMessage(role=MessageRole.USER, content="Hello")])


@pytest.mark.asyncio
async def test_grok_provider_normalizes_503_unavailable_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="Service Unavailable")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = GrokProvider(api_key="xai-test-key", client=client)

    with pytest.raises(ProviderUnavailableError):
        await provider.generate([PromptMessage(role=MessageRole.USER, content="Hello")])


def test_grok_provider_capabilities():
    provider = GrokProvider(api_key="xai-key")
    caps = provider.get_capabilities()
    assert "grok-2" in caps.supported_models
    assert caps.max_context_tokens >= 128000
    assert caps.supports_streaming is True
