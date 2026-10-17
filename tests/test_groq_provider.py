"""Tests for GroqProvider (Groq Cloud) and ultra-fast inference error normalization."""

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
from icarus_core.providers.groq import GroqProvider


def test_groq_provider_conforms_to_protocol():
    provider = GroqProvider(api_key="gsk_test_key_12345678901234567890")
    assert isinstance(provider, ModelProvider)


@pytest.mark.asyncio
async def test_groq_provider_generate_success():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer gsk_test_key"
        payload = json.loads(request.read())
        assert payload["model"] == GroqProvider.DEFAULT_MODEL
        assert payload["stream"] is False

        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-groq-123",
                "model": GroqProvider.DEFAULT_MODEL,
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "Hello from Groq Cloud!",
                        },
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 6, "total_tokens": 16},
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = GroqProvider(api_key="gsk_test_key", client=client)

    result = await provider.generate([PromptMessage(role=MessageRole.USER, content="Hello Groq")])
    assert result.content == "Hello from Groq Cloud!"
    assert result.model == GroqProvider.DEFAULT_MODEL
    assert result.finish_reason == "stop"


@pytest.mark.asyncio
async def test_groq_provider_stream_success():
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.read())
        assert payload["stream"] is True

        sse_body = (
            'data: {"choices":[{"delta":{"content":"Groq"},"finish_reason":null}]}\n\n'
            'data: {"choices":[{"delta":{"content":" fast streaming"},"finish_reason":null}]}\n\n'
            'data: {"choices":[{"delta":{"content":""},"finish_reason":"stop"}]}\n\n'
            "data: [DONE]\n\n"
        )
        return httpx.Response(
            200,
            text=sse_body,
            headers={"Content-Type": "text/event-stream"},
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = GroqProvider(api_key="gsk_test_key", client=client)

    chunks = []
    async for chunk in provider.stream([PromptMessage(role=MessageRole.USER, content="Hello")]):
        chunks.append(chunk)

    deltas = [c.delta for c in chunks]
    assert "".join(deltas) == "Groq fast streaming"
    assert any(c.finish_reason == "stop" for c in chunks)


@pytest.mark.asyncio
async def test_groq_provider_normalizes_401_authentication_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"message": "Invalid Groq API key provided"}})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = GroqProvider(api_key="gsk_bad_key", client=client)

    with pytest.raises(AuthenticationError) as exc_info:
        await provider.generate([PromptMessage(role=MessageRole.USER, content="Hello")])
    assert exc_info.value.provider == "groq"


@pytest.mark.asyncio
async def test_groq_provider_normalizes_429_rate_limit_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": {"message": "Rate limit reached for requests"}})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = GroqProvider(api_key="gsk_test_key", client=client)

    with pytest.raises(RateLimitError) as exc_info:
        await provider.generate([PromptMessage(role=MessageRole.USER, content="Hello")])
    assert exc_info.value.provider == "groq"


@pytest.mark.asyncio
async def test_groq_provider_normalizes_400_context_length():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": {"message": "Context window exceeded"}})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = GroqProvider(api_key="gsk_test_key", client=client)

    with pytest.raises(ContextLengthExceededError) as exc_info:
        await provider.generate([PromptMessage(role=MessageRole.USER, content="Hello")])
    assert exc_info.value.provider == "groq"


@pytest.mark.asyncio
async def test_groq_provider_normalizes_503_unavailable_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="Service Unavailable")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = GroqProvider(api_key="gsk_test_key", client=client)

    with pytest.raises(ProviderUnavailableError) as exc_info:
        await provider.generate([PromptMessage(role=MessageRole.USER, content="Hello")])
    assert exc_info.value.provider == "groq"


def test_groq_provider_capabilities():
    provider = GroqProvider(api_key="gsk_key")
    caps = provider.get_capabilities()
    assert isinstance(caps, ProviderCapabilities)
    assert "llama-3.3-70b-versatile" in caps.supported_models
    assert caps.max_context_tokens >= 128000
    assert caps.supports_streaming is True
