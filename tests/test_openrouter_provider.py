"""Tests for OpenRouterProvider conforming to ModelProvider protocol."""

import json

import httpx
import pytest
from icarus_contracts import (
    AuthenticationError,
    ContextLengthExceededError,
    MessageRole,
    PromptMessage,
    ProviderCapabilities,
    ProviderUnavailableError,
    RateLimitError,
)
from icarus_core.providers.base import ModelProvider
from icarus_core.providers.openrouter import OpenRouterProvider


def test_openrouter_provider_conforms_to_protocol():
    provider = OpenRouterProvider(api_key="sk-or-v1-test-key")
    assert isinstance(provider, ModelProvider)


@pytest.mark.asyncio
async def test_openrouter_provider_generate_success():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer sk-or-v1-test-key"
        assert "HTTP-Referer" in request.headers
        assert "X-Title" in request.headers
        payload = json.loads(request.read())
        assert payload["model"] == "anthropic/claude-3.5-sonnet"
        assert payload["stream"] is False
        assert payload["messages"] == [{"role": "user", "content": "Hello"}]

        return httpx.Response(
            200,
            json={
                "id": "gen-test-123",
                "model": "anthropic/claude-3.5-sonnet",
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "Hello from Claude on OpenRouter!",
                        },
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 5, "completion_tokens": 8, "total_tokens": 13},
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = OpenRouterProvider(api_key="sk-or-v1-test-key", client=client)

    result = await provider.generate([PromptMessage(role=MessageRole.USER, content="Hello")])
    assert result.content == "Hello from Claude on OpenRouter!"
    assert result.model == "anthropic/claude-3.5-sonnet"
    assert result.finish_reason == "stop"
    assert result.usage == {"prompt_tokens": 5, "completion_tokens": 8, "total_tokens": 13}


@pytest.mark.asyncio
async def test_openrouter_provider_stream_success():
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.read())
        assert payload["stream"] is True
        assert payload["model"] == "openai/gpt-4o"

        sse_body = (
            'data: {"choices":[{"delta":{"content":"OpenRouter"},"finish_reason":null}]}\n\n'
            'data: {"choices":[{"delta":{"content":" streaming"},"finish_reason":null}]}\n\n'
            'data: {"choices":[{"delta":{"content":""},"finish_reason":"stop"}]}\n\n'
            "data: [DONE]\n\n"
        )
        return httpx.Response(
            200,
            text=sse_body,
            headers={"Content-Type": "text/event-stream"},
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = OpenRouterProvider(api_key="sk-or-v1-test-key", client=client)

    chunks = []
    async for chunk in provider.stream(
        [PromptMessage(role=MessageRole.USER, content="Stream test")],
        model="openai/gpt-4o",
    ):
        chunks.append(chunk)

    deltas = [c.delta for c in chunks]
    assert "".join(deltas) == "OpenRouter streaming"
    assert any(c.finish_reason == "stop" for c in chunks)


@pytest.mark.asyncio
async def test_openrouter_normalizes_401_authentication_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"message": "Invalid API key"}})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = OpenRouterProvider(api_key="bad-key", client=client)

    with pytest.raises(AuthenticationError) as exc_info:
        await provider.generate([PromptMessage(role=MessageRole.USER, content="Hello")])
    assert exc_info.value.provider == "openrouter"


@pytest.mark.asyncio
async def test_openrouter_normalizes_429_rate_limit_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": {"message": "Rate limit exceeded"}})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = OpenRouterProvider(api_key="sk-or-test", client=client)

    with pytest.raises(RateLimitError) as exc_info:
        await provider.generate([PromptMessage(role=MessageRole.USER, content="Hello")])
    assert exc_info.value.provider == "openrouter"


@pytest.mark.asyncio
async def test_openrouter_normalizes_400_context_length_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": {"message": "Context window limit exceeded"}})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = OpenRouterProvider(api_key="sk-or-test", client=client)

    with pytest.raises(ContextLengthExceededError) as exc_info:
        await provider.generate([PromptMessage(role=MessageRole.USER, content="Hello")])
    assert exc_info.value.provider == "openrouter"


@pytest.mark.asyncio
async def test_openrouter_normalizes_503_unavailable_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="Service Unavailable")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = OpenRouterProvider(api_key="sk-or-test", client=client)

    with pytest.raises(ProviderUnavailableError) as exc_info:
        await provider.generate([PromptMessage(role=MessageRole.USER, content="Hello")])
    assert exc_info.value.provider == "openrouter"


def test_openrouter_provider_capabilities():
    provider = OpenRouterProvider(api_key="sk-or-test")
    caps = provider.get_capabilities()
    assert isinstance(caps, ProviderCapabilities)
    assert "anthropic/claude-3.5-sonnet" in caps.supported_models
    assert caps.max_context_tokens >= 128000
    assert caps.supports_streaming is True
