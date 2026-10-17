"""Provider registry and factory mapping for model adapters."""

from collections.abc import Callable
from typing import Any

from icarus_core.credentials import CredentialResolver
from icarus_core.providers.base import ModelProvider
from icarus_core.providers.grok import GrokProvider
from icarus_core.providers.groq import GroqProvider
from icarus_core.providers.litellm import LiteLLMProvider
from icarus_core.providers.mock import MockProvider
from icarus_core.providers.openrouter import OpenRouterProvider

ProviderFactory = Callable[..., ModelProvider]


class ProviderRegistry:
    """Registry maintaining available ModelProvider adapters and credential-aware instantiation."""

    def __init__(self, resolver: CredentialResolver | None = None) -> None:
        self.resolver = resolver or CredentialResolver()
        self._factories: dict[str, ProviderFactory] = {}
        self._requires_credentials: dict[str, bool] = {}

        # Register default built-in providers
        self.register("mock", lambda **kw: MockProvider(**kw), requires_credentials=False)
        self.register("grok", lambda api_key, **kw: GrokProvider(api_key=api_key, **kw))
        self.register("xai", lambda api_key, **kw: GrokProvider(api_key=api_key, **kw))
        self.register("groq", lambda api_key, **kw: GroqProvider(api_key=api_key, **kw))
        self.register("openrouter", lambda api_key, **kw: OpenRouterProvider(api_key=api_key, **kw))
        self.register(
            "litellm",
            lambda api_key=None, **kw: LiteLLMProvider(
                api_key=api_key or self.resolver.resolve("litellm").secret,
                **kw,
            ),
            requires_credentials=False,
        )

    def register(
        self,
        name: str,
        factory: ProviderFactory,
        requires_credentials: bool = True,
    ) -> None:
        """Register a new provider name with its adapter factory."""
        normalized = name.lower().strip()
        self._factories[normalized] = factory
        self._requires_credentials[normalized] = requires_credentials

    def list_supported_providers(self) -> list[str]:
        """Return the list of all registered provider names."""
        return sorted(self._factories.keys())

    def get_provider(
        self,
        name: str,
        api_key: str | None = None,
        **kwargs: Any,
    ) -> ModelProvider:
        """Instantiate a ModelProvider by name, resolving credentials when required."""
        normalized = name.lower().strip()
        if normalized not in self._factories:
            supported = ", ".join(self.list_supported_providers())
            raise ValueError(f"Unsupported provider '{name}'. Supported providers: {supported}")

        factory = self._factories[normalized]
        needs_credentials = self._requires_credentials.get(normalized, True)

        if not needs_credentials:
            return factory(**kwargs)

        # Real provider resolution
        effective_key = api_key
        if not effective_key:
            cred = self.resolver.resolve_or_raise(normalized)
            effective_key = cred.secret

        if effective_key is None:
            raise ValueError(f"No valid API key available for provider '{name}'.")

        return factory(api_key=effective_key, **kwargs)
