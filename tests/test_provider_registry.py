"""Tests for ProviderRegistry factory mapping and credential resolution."""

from unittest.mock import MagicMock

import pytest
from icarus_contracts import CredentialResult, CredentialSource
from icarus_core.credentials import CredentialNotFoundError
from icarus_core.providers.grok import GrokProvider
from icarus_core.providers.mock import MockProvider
from icarus_core.providers.registry import ProviderRegistry


def test_registry_get_mock_provider():
    registry = ProviderRegistry()
    provider = registry.get_provider("mock")
    assert isinstance(provider, MockProvider)


def test_registry_get_grok_with_explicit_key():
    registry = ProviderRegistry()
    provider = registry.get_provider("grok", api_key="xai-explicit-key")
    assert isinstance(provider, GrokProvider)
    assert provider.api_key == "xai-explicit-key"


def test_registry_resolves_credential_via_resolver():
    mock_resolver = MagicMock()
    mock_resolver.resolve_or_raise.return_value = CredentialResult(
        provider="grok",
        secret="xai-resolved-key",
        source=CredentialSource.KEYRING,
        masked="xai-...-key",
    )

    registry = ProviderRegistry(resolver=mock_resolver)
    provider = registry.get_provider("grok")
    assert isinstance(provider, GrokProvider)
    assert provider.api_key == "xai-resolved-key"
    mock_resolver.resolve_or_raise.assert_called_once_with("grok")


def test_registry_raises_on_missing_credential():
    mock_resolver = MagicMock()
    mock_resolver.resolve_or_raise.side_effect = CredentialNotFoundError("grok")

    registry = ProviderRegistry(resolver=mock_resolver)
    with pytest.raises(CredentialNotFoundError):
        registry.get_provider("grok")


def test_registry_raises_on_unsupported_provider():
    registry = ProviderRegistry()
    with pytest.raises(ValueError) as exc_info:
        registry.get_provider("nonexistent-provider")
    assert "unsupported" in str(exc_info.value).lower()


def test_registry_custom_provider_registration():
    registry = ProviderRegistry()
    custom_mock = MockProvider(responses=["Custom registered provider"])
    registry.register("custom-fast", lambda **kw: custom_mock, requires_credentials=False)

    assert "custom-fast" in registry.list_supported_providers()
    provider = registry.get_provider("custom-fast")
    assert provider is custom_mock
