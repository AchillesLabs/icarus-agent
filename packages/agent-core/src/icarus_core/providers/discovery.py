"""Dynamic model catalog discovery and classification (Free vs Paid/Standard tiers)."""

from typing import Any

import httpx
from icarus_contracts import DiscoveredModel


def fetch_groq_models(
    api_key: str,
    base_url: str = "https://api.groq.com/openai/v1",
    client: httpx.Client | None = None,
) -> list[DiscoveredModel]:
    """Fetch and classify active chat models accessible on a Groq Cloud API key."""
    if not api_key or not api_key.strip():
        return []

    url = f"{base_url.rstrip('/')}/models"
    headers = {
        "Authorization": f"Bearer {api_key.strip()}",
        "Content-Type": "application/json",
    }

    try:
        if client is not None:
            resp = client.get(url, headers=headers, timeout=10.0)
        else:
            with httpx.Client(timeout=10.0) as http_client:
                resp = http_client.get(url, headers=headers)

        if resp.is_error:
            return []

        data: list[dict[str, Any]] = resp.json().get("data", [])
        free_models: list[DiscoveredModel] = []
        paid_models: list[DiscoveredModel] = []

        for m in data:
            if not m.get("active", True):
                continue

            mid = str(m.get("id", ""))
            output_mods = m.get("output_modalities", ["text"])
            ctx = int(m.get("context_window", 0))

            # Filter out non-chat / specialized audio / guard models
            if "transcription" in output_mods or "speech" in output_mods:
                continue
            if any(kw in mid.lower() for kw in ["prompt-guard", "safeguard", "whisper", "orpheus"]):
                continue
            if ctx < 1000:
                continue

            pricing = m.get("pricing")
            prompt_cost = 0.0
            comp_cost = 0.0
            if isinstance(pricing, dict):
                try:
                    prompt_cost = float(pricing.get("prompt", 0) or 0)
                    comp_cost = float(pricing.get("completion", 0) or 0)
                except (ValueError, TypeError):
                    prompt_cost = 0.0
                    comp_cost = 0.0

            is_free = prompt_cost == 0.0 and comp_cost == 0.0
            tier = "Free" if is_free else "Paid / Standard"

            if is_free:
                pricing_info = "Free (Complimentary / 0 Cost)"
            else:
                p_in = prompt_cost * 1_000_000
                p_out = comp_cost * 1_000_000
                pricing_info = f"${p_in:.2f}/1M in, ${p_out:.2f}/1M out (Free Dev Tier)"

            model_obj = DiscoveredModel(
                id=mid,
                name=str(m.get("name") or mid),
                provider="groq",
                context_window=ctx,
                is_free=is_free,
                tier=tier,
                pricing_info=pricing_info,
                description=f"Groq Cloud chat model with {ctx:,} token context window.",
            )

            if is_free:
                free_models.append(model_obj)
            else:
                paid_models.append(model_obj)

        # Sort free models, then paid models deterministically by context window desc, then ID
        free_models.sort(key=lambda x: (-x.context_window, x.id))
        paid_models.sort(key=lambda x: (-x.context_window, x.id))
        return free_models + paid_models

    except Exception:
        return []


def fetch_openrouter_models(
    api_key: str | None = None,
    base_url: str = "https://openrouter.ai/api/v1",
    client: httpx.Client | None = None,
) -> list[DiscoveredModel]:
    """Fetch and classify chat models from OpenRouter catalog."""
    url = f"{base_url.rstrip('/')}/models"
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if api_key and api_key.strip():
        headers["Authorization"] = f"Bearer {api_key.strip()}"

    try:
        if client is not None:
            resp = client.get(url, headers=headers, timeout=10.0)
        else:
            with httpx.Client(timeout=10.0) as http_client:
                resp = http_client.get(url, headers=headers)

        if resp.is_error:
            return []

        data: list[dict[str, Any]] = resp.json().get("data", [])
        free_models: list[DiscoveredModel] = []
        paid_models: list[DiscoveredModel] = []

        for m in data:
            mid = str(m.get("id", ""))
            name = str(m.get("name") or mid)
            ctx = int(m.get("context_length", 128000))
            pricing = m.get("pricing") or {}

            prompt_cost = 0.0
            comp_cost = 0.0
            if isinstance(pricing, dict):
                try:
                    prompt_cost = float(pricing.get("prompt", 0) or 0)
                    comp_cost = float(pricing.get("completion", 0) or 0)
                except (ValueError, TypeError):
                    prompt_cost = 0.0
                    comp_cost = 0.0

            is_free = mid.endswith(":free") or (prompt_cost == 0.0 and comp_cost == 0.0)
            tier = "Free" if is_free else "Paid / Standard"

            if is_free:
                pricing_info = "Free ($0 / 1M tokens)"
            else:
                pricing_info = f"${prompt_cost * 1_000_000:.2f}/1M tokens"

            model_obj = DiscoveredModel(
                id=mid,
                name=name,
                provider="openrouter",
                context_window=ctx,
                is_free=is_free,
                tier=tier,
                pricing_info=pricing_info,
                description=str(m.get("description") or ""),
            )

            if is_free:
                free_models.append(model_obj)
            else:
                paid_models.append(model_obj)

        free_models.sort(key=lambda x: x.context_window, reverse=True)
        # Limit paid models to top 30 to avoid overwhelming CLI
        return free_models + paid_models[:30]

    except Exception:
        return []


def fetch_grok_models() -> list[DiscoveredModel]:
    """Return catalog of known xAI Grok models."""
    return [
        DiscoveredModel(
            id="grok-2",
            name="Grok 2",
            provider="grok",
            context_window=131072,
            is_free=False,
            tier="Paid / Standard",
            pricing_info="$2.00/1M prompt, $10.00/1M completion",
            description="State-of-the-art flagship reasoning and vision model by xAI.",
        ),
        DiscoveredModel(
            id="grok-2-mini",
            name="Grok 2 Mini",
            provider="grok",
            context_window=131072,
            is_free=False,
            tier="Paid / Standard",
            pricing_info="$0.20/1M prompt, $1.00/1M completion",
            description="High-speed, cost-efficient reasoning model by xAI.",
        ),
        DiscoveredModel(
            id="grok-beta",
            name="Grok Beta",
            provider="grok",
            context_window=131072,
            is_free=False,
            tier="Paid / Standard",
            pricing_info="$5.00/1M prompt, $15.00/1M completion",
            description="Experimental preview model by xAI.",
        ),
    ]


def fetch_mock_models() -> list[DiscoveredModel]:
    """Return catalog of mock test models."""
    return [
        DiscoveredModel(
            id="mock-model-v1",
            name="Mock Model V1",
            provider="mock",
            context_window=128000,
            is_free=True,
            tier="Free",
            pricing_info="Free (Local In-Memory)",
            description="Offline test harness model.",
        ),
        DiscoveredModel(
            id="mock-model-v2",
            name="Mock Model V2",
            provider="mock",
            context_window=64000,
            is_free=True,
            tier="Free",
            pricing_info="Free (Local In-Memory)",
            description="Offline secondary test harness model.",
        ),
    ]


def fetch_provider_models(
    provider: str,
    api_key: str | None = None,
    client: httpx.Client | None = None,
) -> list[DiscoveredModel]:
    """Unified dispatcher for fetching and classifying models by provider."""
    normalized = provider.lower().strip()
    if normalized == "groq":
        return fetch_groq_models(api_key=api_key or "", client=client)
    if normalized == "openrouter":
        return fetch_openrouter_models(api_key=api_key, client=client)
    if normalized in {"grok", "xai"}:
        return fetch_grok_models()
    if normalized == "mock":
        return fetch_mock_models()
    return []
