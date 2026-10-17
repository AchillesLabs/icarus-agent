"""Model providers package defining ModelProvider and adapter implementations."""

from icarus_core.providers.base import ModelProvider
from icarus_core.providers.discovery import (
    fetch_groq_models,
    fetch_openrouter_models,
    fetch_provider_models,
)
from icarus_core.providers.grok import GrokProvider
from icarus_core.providers.groq import GroqProvider
from icarus_core.providers.litellm import LiteLLMProvider
from icarus_core.providers.mock import MockProvider
from icarus_core.providers.openrouter import OpenRouterProvider
from icarus_core.providers.registry import ProviderRegistry

__all__ = [
    "GrokProvider",
    "GroqProvider",
    "LiteLLMProvider",
    "MockProvider",
    "ModelProvider",
    "OpenRouterProvider",
    "ProviderRegistry",
    "fetch_groq_models",
    "fetch_openrouter_models",
    "fetch_provider_models",
]
