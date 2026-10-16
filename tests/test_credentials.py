"""Tests for CredentialResolver and the 4-tier resolution pipeline."""

from unittest.mock import MagicMock, patch

import pytest
from icarus_contracts import CredentialSource
from icarus_core.credentials import (
    CredentialNotFoundError,
    CredentialResolver,
    mask_secret,
)


def test_mask_secret():
    assert mask_secret(None) is None
    assert mask_secret("") is None
    assert mask_secret("short") == "s***t"

    masked = mask_secret("xai-1234567890abcdef1234")
    assert masked.startswith("xai-")
    assert masked.endswith("1234")
    assert "1234567890abcdef" not in masked
    assert "..." in masked


def test_resolution_tier_1_cli_arg_takes_highest_precedence():
    resolver = CredentialResolver()
    with (
        patch.dict("os.environ", {"XAI_API_KEY": "env-secret"}),
        patch("keyring.get_password", return_value="keyring-secret"),
    ):
        result = resolver.resolve("grok", cli_arg="cli-override-secret")
        assert result.source == CredentialSource.CLI_ARG
        assert result.secret == "cli-override-secret"
        assert result.is_available is True


def test_resolution_tier_2_env_var_takes_precedence_over_keyring():
    resolver = CredentialResolver()
    # Grok specific env var
    with (
        patch.dict("os.environ", {"XAI_API_KEY": "xai-env-key"}, clear=True),
        patch("keyring.get_password", return_value="keyring-secret"),
    ):
        result = resolver.resolve("grok")
        assert result.source == CredentialSource.ENV_VAR
        assert result.secret == "xai-env-key"

    # OpenRouter specific env var
    with (
        patch.dict("os.environ", {"OPENROUTER_API_KEY": "sk-or-env-key"}, clear=True),
        patch("keyring.get_password", return_value="keyring-secret"),
    ):
        result = resolver.resolve("openrouter")
        assert result.source == CredentialSource.ENV_VAR
        assert result.secret == "sk-or-env-key"

    # Generic ICARUS_API_KEY fallback
    with (
        patch.dict("os.environ", {"ICARUS_API_KEY": "icarus-shared-key"}, clear=True),
        patch("keyring.get_password", return_value="keyring-secret"),
    ):
        result = resolver.resolve("grok")
        assert result.source == CredentialSource.ENV_VAR
        assert result.secret == "icarus-shared-key"


def test_resolution_tier_3_os_keyring_used_when_no_cli_or_env():
    resolver = CredentialResolver()
    with (
        patch.dict("os.environ", {}, clear=True),
        patch("keyring.get_password", return_value="keyring-vault-key"),
    ):
        result = resolver.resolve("grok")
        assert result.source == CredentialSource.KEYRING
        assert result.secret == "keyring-vault-key"
        assert result.is_available is True
        assert result.masked is not None


def test_resolution_tier_4_missing_returns_none():
    resolver = CredentialResolver()
    with patch.dict("os.environ", {}, clear=True), patch("keyring.get_password", return_value=None):
        result = resolver.resolve("grok")
        assert result.source == CredentialSource.NONE
        assert result.secret is None
        assert result.is_available is False


def test_resolve_or_raise_raises_credential_not_found():
    resolver = CredentialResolver()
    with patch.dict("os.environ", {}, clear=True), patch("keyring.get_password", return_value=None):
        with pytest.raises(CredentialNotFoundError) as exc_info:
            resolver.resolve_or_raise("grok")
        assert "XAI_API_KEY" in exc_info.value.fix_hint
        assert "icarus init" in exc_info.value.fix_hint


def test_store_and_delete_credentials_in_keyring():
    resolver = CredentialResolver()
    mock_set = MagicMock()
    mock_del = MagicMock()

    with patch("keyring.set_password", mock_set), patch("keyring.delete_password", mock_del):
        resolver.store("grok", "my-new-secret")
        mock_set.assert_called_once_with("icarus", "grok", "my-new-secret")

        resolver.delete("grok")
        mock_del.assert_called_once_with("icarus", "grok")
