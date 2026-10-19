"""Integration tests for remote security CLI commands (icarus vault and icarus token)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from httpx import ASGITransport
from icarus_api.app import create_app
from icarus_api.config import ApiSettings
from icarus_cli.main import app as cli_app
from icarus_cli.remote import RemoteAgentClient
from icarus_core.config import ConfigManager
from icarus_core.persistence.database import DatabaseManager
from icarus_core.persistence.models import Base
from icarus_core.security import CredentialVault
from typer.testing import CliRunner

runner = CliRunner(env={"COLUMNS": "160"})


@pytest.fixture
def test_env(tmp_path: Path):
    """Provide isolated configuration directory and mock OS keyring."""
    config_file = tmp_path / "config.toml"
    mock_keyring: dict[str, str] = {}

    def get_password(service: str, username: str):
        return mock_keyring.get(f"{service}:{username}")

    def set_password(service: str, username: str, password: str):
        mock_keyring[f"{service}:{username}"] = password

    def delete_password(service: str, username: str):
        mock_keyring.pop(f"{service}:{username}", None)

    with (
        patch("icarus_core.paths.get_icarus_home", return_value=tmp_path),
        patch("icarus_core.config.get_icarus_config_path", return_value=config_file),
        patch("keyring.get_password", side_effect=get_password),
        patch("keyring.set_password", side_effect=set_password),
        patch("keyring.delete_password", side_effect=delete_password),
    ):
        cfg_mgr = ConfigManager(config_path=config_file)
        yield cfg_mgr, tmp_path


@pytest.fixture
def api_test_app():
    """Create in-memory test FastAPI application with active master vault key and auth."""
    db_manager = DatabaseManager(db_url="sqlite:///:memory:")
    Base.metadata.create_all(db_manager.engine)
    settings = ApiSettings(
        auth_tokens={
            "sk-test-admin-token": "tenant-sec-ops",
        }
    )
    vault = CredentialVault(master_key="security-cli-vault-master-key-12345")
    app = create_app(
        settings=settings,
        db_manager=db_manager,
        credential_vault=vault,
    )
    return app


@pytest.fixture
def remote_client(api_test_app):
    """Provide a configured RemoteAgentClient connected to the in-memory FastAPI app."""
    transport = ASGITransport(app=api_test_app)
    return RemoteAgentClient(
        base_url="http://testserver",
        api_key="sk-test-admin-token",
        transport=transport,
    )


# ============================================================================
# RemoteAgentClient Direct Unit Tests
# ============================================================================


@pytest.mark.asyncio
async def test_remote_client_vault_methods(remote_client: RemoteAgentClient):
    """Verify RemoteAgentClient vault CRUD methods over HTTP."""
    # 1. Set Groq key
    res = await remote_client.set_vault_credential(
        provider="groq", api_key="gsk_1234567890abcdef1234"
    )
    assert res.provider == "groq"
    assert res.key_hint == "gsk...1234"

    # 2. List vault keys
    creds = await remote_client.list_vault_credentials()
    assert len(creds) == 1
    assert creds[0].provider == "groq"
    assert creds[0].key_hint == "gsk...1234"

    # 3. Delete vault key
    del_res = await remote_client.delete_vault_credential("groq")
    assert del_res.deleted is True
    assert del_res.provider == "groq"

    # 4. List again is empty
    creds_after = await remote_client.list_vault_credentials()
    assert len(creds_after) == 0


@pytest.mark.asyncio
async def test_remote_client_token_methods(remote_client: RemoteAgentClient):
    """Verify RemoteAgentClient token lifecycle methods over HTTP."""
    # 1. Create API token
    created = await remote_client.create_api_token(name="test-runner")
    assert created.name == "test-runner"
    assert created.token.startswith("sk_icarus_")
    assert created.is_active is True

    # 2. List tokens
    tokens = await remote_client.list_api_tokens(include_revoked=True)
    assert len(tokens) == 1
    assert tokens[0].id == created.id
    assert tokens[0].is_active is True

    # 3. Revoke token
    revoked = await remote_client.revoke_api_token(created.id)
    assert revoked.id == created.id
    assert revoked.is_active is False
    assert revoked.revoked_at is not None

    # 4. List active-only should be empty
    active_tokens = await remote_client.list_api_tokens(include_revoked=False)
    assert len(active_tokens) == 0


# ============================================================================
# icarus vault CLI Commands
# ============================================================================


def test_vault_cli_no_server_error(test_env):
    """Verify icarus vault commands error clearly when no server profile exists."""
    result = runner.invoke(cli_app, ["vault", "list"])
    assert result.exit_code == 1
    assert "No remote server profile found" in result.stdout


def test_vault_cli_lifecycle(test_env, remote_client: RemoteAgentClient):
    """Test icarus vault set, list, and remove end-to-end against remote server."""
    cfg_mgr, _ = test_env
    cfg_mgr.add_server("prod", "http://testserver", api_key="sk-test-admin-token", active=True)

    with patch("icarus_cli.vault_cmd.resolve_remote_client", return_value=remote_client):
        # 1. Initially empty
        res = runner.invoke(cli_app, ["vault", "list"])
        assert res.exit_code == 0
        assert "No provider credentials configured in server vault" in res.stdout

        # 2. Set OpenRouter key with --key
        res = runner.invoke(
            cli_app,
            ["vault", "set", "openrouter", "--key", "sk-or-v1-abcdef12345678904a2b"],
        )
        assert res.exit_code == 0
        assert "Successfully stored encrypted credential for provider 'openrouter'" in res.stdout
        assert "sk-...4a2b" in res.stdout

        # 3. Set Groq key via interactive prompt
        res = runner.invoke(
            cli_app,
            ["vault", "set", "groq"],
            input="gsk_1234567890abcdef\n",
        )
        assert res.exit_code == 0
        assert "Successfully stored encrypted credential for provider 'groq'" in res.stdout

        # 4. List credentials in Rich table
        res = runner.invoke(cli_app, ["vault", "list"])
        assert res.exit_code == 0
        assert "Server BYOK Provider Credentials" in res.stdout
        assert "openrouter" in res.stdout
        assert "sk-...4a2b" in res.stdout
        assert "groq" in res.stdout
        assert "gsk...cdef" in res.stdout

        # 5. Remove OpenRouter credential
        res = runner.invoke(cli_app, ["vault", "remove", "openrouter"])
        assert res.exit_code == 0
        assert "Removed credential for provider 'openrouter' from server vault" in res.stdout

        # 6. Removing non-existent credential fails cleanly
        res = runner.invoke(cli_app, ["vault", "remove", "non-existent"])
        assert res.exit_code == 1
        assert "Error:" in res.stdout


# ============================================================================
# icarus token CLI Commands
# ============================================================================


def test_token_cli_no_server_error(test_env):
    """Verify icarus token commands error clearly when no server profile exists."""
    result = runner.invoke(cli_app, ["token", "list"])
    assert result.exit_code == 1
    assert "No remote server profile found" in result.stdout


def test_token_cli_lifecycle(test_env, remote_client: RemoteAgentClient):
    """Test icarus token create, list, and revoke end-to-end against remote server."""
    cfg_mgr, _ = test_env
    cfg_mgr.add_server("prod", "http://testserver", api_key="sk-test-admin-token", active=True)

    with patch("icarus_cli.token_cmd.resolve_remote_client", return_value=remote_client):
        # 1. Initially empty
        res = runner.invoke(cli_app, ["token", "list"])
        assert res.exit_code == 0
        assert "No API tokens found on remote server" in res.stdout

        # 2. Create first token
        res = runner.invoke(cli_app, ["token", "create", "ci-builder"])
        assert res.exit_code == 0
        assert "API Token Created Successfully!" in res.stdout
        assert "ci-builder" in res.stdout
        assert "sk_icarus_" in res.stdout
        assert "WARNING" in res.stdout

        # 3. Create second token
        res = runner.invoke(cli_app, ["token", "create", "staging-server"])
        assert res.exit_code == 0
        assert "staging-server" in res.stdout

        # 4. List tokens
        res = runner.invoke(cli_app, ["token", "list"])
        assert res.exit_code == 0
        assert "Remote API Access Tokens" in res.stdout
        assert "ci-builder" in res.stdout
        assert "staging-server" in res.stdout
        assert "ACTIVE" in res.stdout

        # Extract token ID of first token from list to revoke
        tokens = asyncio_run(remote_client.list_api_tokens(include_revoked=True))
        ci_token = next(t for t in tokens if t.name == "ci-builder")

        # 5. Revoke token
        res = runner.invoke(cli_app, ["token", "revoke", ci_token.id])
        assert res.exit_code == 0
        assert f"Successfully revoked API token '{ci_token.name}' ({ci_token.id})" in res.stdout

        # 6. List with --all shows REVOKED badge
        res = runner.invoke(cli_app, ["token", "list", "--all"])
        assert res.exit_code == 0
        assert "REVOKED" in res.stdout

        # 7. Revoke non-existent token fails cleanly with exit code 1
        res = runner.invoke(cli_app, ["token", "revoke", "non-existent-uuid-1234"])
        assert res.exit_code == 1
        assert "Error:" in res.stdout

        # 8. List with --active-only hides the revoked token
        res = runner.invoke(cli_app, ["token", "list", "--active-only"])
        assert res.exit_code == 0
        assert "staging-server" in res.stdout
        assert ci_token.id not in res.stdout


def test_resolve_remote_client_custom_server_profile(test_env):
    """Test resolve_remote_client resolves explicit --server profile and fallback to active."""
    from icarus_cli.vault_cmd import resolve_remote_client

    cfg_mgr, _ = test_env
    cfg_mgr.add_server("backup", "https://backup.icarus.ai", api_key="sk-backup-key", active=False)
    cfg_mgr.add_server(
        "primary", "https://primary.icarus.ai", api_key="sk-primary-key", active=True
    )

    # 1. Resolve default (active = primary)
    client_default = resolve_remote_client()
    assert client_default.base_url == "https://primary.icarus.ai"
    assert client_default.api_key == "sk-primary-key"

    # 2. Resolve explicit profile (backup)
    client_custom = resolve_remote_client(server="backup")
    assert client_custom.base_url == "https://backup.icarus.ai"
    assert client_custom.api_key == "sk-backup-key"


def asyncio_run(coro):
    import asyncio

    return asyncio.run(coro)
