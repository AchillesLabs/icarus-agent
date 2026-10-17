"""Tests for LiteLLM gateway adapter conforming to ModelProvider protocol."""

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
from icarus_core.providers.litellm import LiteLLMProvider


def test_litellm_provider_conforms_to_protocol():
    provider = LiteLLMProvider(api_key="sk-litellm-test", api_base="http://localhost:4000/v1")
    assert isinstance(provider, ModelProvider)


@pytest.mark.asyncio
async def test_litellm_gateway_generate_success():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer sk-litellm-test"
        payload = json.loads(request.read())
        assert payload["model"] == "gpt-4o"
        assert payload["stream"] is False

        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-litellm-1",
                "model": "gpt-4o",
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "Response via LiteLLM gateway.",
                        },
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 12, "completion_tokens": 6, "total_tokens": 18},
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = LiteLLMProvider(
        api_key="sk-litellm-test",
        api_base="http://localhost:4000/v1",
        client=client,
    )

    result = await provider.generate(
        [PromptMessage(role=MessageRole.USER, content="Hello gateway")]
    )
    assert result.content == "Response via LiteLLM gateway."
    assert result.model == "gpt-4o"
    assert result.finish_reason == "stop"


@pytest.mark.asyncio
async def test_litellm_gateway_stream_success():
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.read())
        assert payload["stream"] is True

        sse_body = (
            'data: {"choices":[{"delta":{"content":"LiteLLM"},"finish_reason":null}]}\n\n'
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
    provider = LiteLLMProvider(
        api_key="sk-litellm-test",
        api_base="http://localhost:4000/v1",
        client=client,
    )

    chunks = []
    async for chunk in provider.stream([PromptMessage(role=MessageRole.USER, content="Hello")]):
        chunks.append(chunk)

    deltas = [c.delta for c in chunks]
    assert "".join(deltas) == "LiteLLM streaming"
    assert any(c.finish_reason == "stop" for c in chunks)


@pytest.mark.asyncio
async def test_litellm_gateway_normalizes_auth_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"message": "Invalid LiteLLM master key"}})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = LiteLLMProvider(
        api_key="bad-key",
        api_base="http://localhost:4000/v1",
        client=client,
    )

    with pytest.raises(AuthenticationError) as exc_info:
        await provider.generate([PromptMessage(role=MessageRole.USER, content="Hello")])
    assert exc_info.value.provider == "litellm"


@pytest.mark.asyncio
async def test_litellm_gateway_normalizes_rate_limit():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            429,
            json={"error": {"message": "LiteLLM rate limit or budget exceeded"}},
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = LiteLLMProvider(
        api_key="key",
        api_base="http://localhost:4000/v1",
        client=client,
    )

    with pytest.raises(RateLimitError) as exc_info:
        await provider.generate([PromptMessage(role=MessageRole.USER, content="Hello")])
    assert exc_info.value.provider == "litellm"


@pytest.mark.asyncio
async def test_litellm_gateway_normalizes_context_length():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            json={"error": {"message": "Prompt context exceeds maximum token length"}},
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = LiteLLMProvider(
        api_key="key",
        api_base="http://localhost:4000/v1",
        client=client,
    )

    with pytest.raises(ContextLengthExceededError) as exc_info:
        await provider.generate([PromptMessage(role=MessageRole.USER, content="Hello")])
    assert exc_info.value.provider == "litellm"


@pytest.mark.asyncio
async def test_litellm_gateway_normalizes_502_bad_gateway():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(502, text="Bad Gateway upstream provider unreachable")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = LiteLLMProvider(api_key="key", api_base="http://localhost:4000/v1", client=client)

    with pytest.raises(ProviderUnavailableError) as exc_info:
        await provider.generate([PromptMessage(role=MessageRole.USER, content="Hello")])
    assert exc_info.value.provider == "litellm"


def test_litellm_capabilities():
    provider = LiteLLMProvider()
    caps = provider.get_capabilities()
    assert isinstance(caps, ProviderCapabilities)
    assert caps.supports_streaming is True
    assert caps.supports_tools is True
