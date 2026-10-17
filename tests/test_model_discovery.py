"""Unit tests for model catalog discovery and Free vs Paid tier classification."""

import httpx
from icarus_core.providers.discovery import (
    fetch_grok_models,
    fetch_groq_models,
    fetch_mock_models,
    fetch_openrouter_models,
    fetch_provider_models,
)


def test_fetch_mock_models():
    models = fetch_mock_models()
    assert len(models) == 2
    assert all(m.provider == "mock" for m in models)
    assert all(m.is_free for m in models)
    assert models[0].id == "mock-model-v1"


def test_fetch_grok_models():
    models = fetch_grok_models()
    assert len(models) == 3
    ids = [m.id for m in models]
    assert "grok-2" in ids
    assert "grok-2-mini" in ids
    assert all(m.provider == "grok" for m in models)
    assert all(not m.is_free for m in models)


def test_fetch_groq_models_empty_key():
    assert fetch_groq_models(api_key="") == []
    assert fetch_groq_models(api_key="   ") == []


def test_fetch_groq_models_with_mock_client():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer gsk_dummy_123"
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": "openai/gpt-oss-120b",
                        "name": "GPT OSS 120B",
                        "active": True,
                        "context_window": 131072,
                        "output_modalities": ["text"],
                        "pricing": {"prompt": "0.00000015", "completion": "0.0000006"},
                    },
                    {
                        "id": "allam-2-7b",
                        "name": "ALLaM-2-7b",
                        "active": True,
                        "context_window": 4096,
                        "output_modalities": ["text"],
                        "pricing": {},
                    },
                    {
                        "id": "whisper-large-v3",
                        "name": "Whisper Large V3",
                        "active": True,
                        "context_window": 448,
                        "output_modalities": ["transcription"],
                    },
                    {
                        "id": "meta-llama/llama-prompt-guard-2-86m",
                        "name": "Prompt Guard",
                        "active": True,
                        "context_window": 512,
                    },
                ]
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    models = fetch_groq_models(api_key="gsk_dummy_123", client=client)

    # Audio & prompt guard should be filtered out
    assert len(models) == 2
    free = [m for m in models if m.is_free]
    paid = [m for m in models if not m.is_free]

    assert len(free) == 1
    assert free[0].id == "allam-2-7b"
    assert free[0].tier == "Free"

    assert len(paid) == 1
    assert paid[0].id == "openai/gpt-oss-120b"
    assert paid[0].tier == "Paid / Standard"
    assert "Free Dev Tier" in paid[0].pricing_info


def test_fetch_openrouter_models_with_mock_client():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": "anthropic/claude-3.5-sonnet",
                        "name": "Claude 3.5 Sonnet",
                        "context_length": 200000,
                        "pricing": {"prompt": "0.000003", "completion": "0.000015"},
                    },
                    {
                        "id": "meta-llama/llama-3.1-8b-instruct:free",
                        "name": "Llama 3.1 8B (Free)",
                        "context_length": 131072,
                        "pricing": {"prompt": "0", "completion": "0"},
                    },
                ]
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    models = fetch_openrouter_models(api_key="sk-or-test", client=client)

    assert len(models) == 2
    free = [m for m in models if m.is_free]
    paid = [m for m in models if not m.is_free]

    assert len(free) == 1
    assert free[0].id == "meta-llama/llama-3.1-8b-instruct:free"

    assert len(paid) == 1
    assert paid[0].id == "anthropic/claude-3.5-sonnet"


def test_fetch_provider_models_dispatcher():
    mock_models = fetch_provider_models("mock")
    assert len(mock_models) == 2

    grok_models = fetch_provider_models("grok")
    assert len(grok_models) == 3

    unknown = fetch_provider_models("nonexistent-provider")
    assert unknown == []
