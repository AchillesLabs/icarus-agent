"""Integration tests for remote server profile management and remote execution parity."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from httpx import ASGITransport
from icarus_api import ApiSettings, create_app
from icarus_cli.chat import run_chat
from icarus_cli.main import app as cli_app
from icarus_cli.observer import RichAgentObserver
from icarus_cli.remote import RemoteAgentClient, RemoteRunResult
from icarus_cli.run import execute_run
from icarus_contracts import ToolCall
from icarus_core.config import ConfigManager
from icarus_core.persistence import Base, DatabaseManager
from icarus_core.providers import ProviderRegistry
from icarus_core.providers.mock import MockProvider
from rich.console import Console
from typer.testing import CliRunner

runner = CliRunner()


@pytest.fixture
def test_env(tmp_path: Path):
    """Provide isolated configuration directory and mock OS keyring."""
    config_file = tmp_path / "config.toml"
    mock_keyring = {}

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
    """Create in-memory test FastAPI application with MockProvider."""
    db_manager = DatabaseManager("sqlite:///:memory:")
    Base.metadata.create_all(db_manager.engine)
    settings = ApiSettings(
        auth_tokens={
            "sk-test-token": "test-tenant",
        }
    )
    provider_registry = ProviderRegistry()
    mock_provider = MockProvider(
        responses=["Remote execution stream works!"],
        canned_chunks=["Remote ", "execution ", "stream ", "works!"],
        tool_calls_sequence=[
            [
                ToolCall(
                    id="call-1",
                    name="search",
                    arguments={"query": "test query"},
                )
            ],
            None,
        ],
    )
    provider_registry.register("mock", lambda **kw: mock_provider, requires_credentials=False)
    app = create_app(
        settings=settings,
        db_manager=db_manager,
        provider_registry=provider_registry,
    )
    return app


# ============================================================================
# Server Profile CLI Command Tests (icarus server add/list/switch/remove)
# ============================================================================


def test_server_cli_add_and_list(test_env):
    """Test registering server profiles and listing them in a formatted table."""
    cfg_mgr, _ = test_env

    # 1. Add primary server profile with token
    result = runner.invoke(
        cli_app,
        ["server", "add", "prod", "https://api.icarus.ai", "--key", "secret-token-1"],
    )
    assert result.exit_code == 0
    assert "Added remote server profile 'prod'" in result.stdout
    assert "active" in result.stdout

    # 2. Add secondary profile without activating
    result = runner.invoke(
        cli_app,
        ["server", "add", "staging", "https://staging.icarus.ai", "--no-activate"],
    )
    assert result.exit_code == 0
    assert "inactive" in result.stdout

    # 3. List servers
    result = runner.invoke(cli_app, ["server", "list"])
    assert result.exit_code == 0
    assert "Configured Remote Icarus Servers" in result.stdout
    assert "prod" in result.stdout
    assert "staging" in result.stdout
    assert "ACTIVE" in result.stdout
    assert "Token Set" in result.stdout


def test_server_cli_switch_and_remove(test_env):
    """Test switching active server profile and removing configured profiles."""
    cfg_mgr, _ = test_env

    runner.invoke(cli_app, ["server", "add", "s1", "https://s1.icarus.ai"])
    runner.invoke(cli_app, ["server", "add", "s2", "https://s2.icarus.ai", "--no-activate"])

    # Verify initial active server
    assert cfg_mgr.load_config().active_server == "s1"

    # Switch active server to s2
    result = runner.invoke(cli_app, ["server", "switch", "s2"])
    assert result.exit_code == 0
    assert "Switched active remote server to 's2'" in result.stdout
    assert cfg_mgr.load_config().active_server == "s2"

    # Switch to nonexistent server errors
    result = runner.invoke(cli_app, ["server", "switch", "nonexistent"])
    assert result.exit_code == 1
    assert "not found" in result.stdout

    # Remove profile s1
    result = runner.invoke(cli_app, ["server", "remove", "s1"])
    assert result.exit_code == 0
    assert "Removed remote server profile 's1'" in result.stdout

    # Remove nonexistent profile errors
    result = runner.invoke(cli_app, ["server", "remove", "nonexistent"])
    assert result.exit_code == 1
    assert "not found" in result.stdout


def test_server_cli_list_empty(test_env):
    """Test listing servers when none are configured."""
    result = runner.invoke(cli_app, ["server", "list"])
    assert result.exit_code == 0
    assert "No remote server profiles configured" in result.stdout


# ============================================================================
# RemoteAgentClient Integration Tests (HTTP & SSE Streaming)
# ============================================================================


@pytest.mark.asyncio
async def test_remote_client_health_and_sessions(api_test_app):
    """Test RemoteAgentClient health probe and session CRUD operations."""
    transport = ASGITransport(app=api_test_app)
    client = RemoteAgentClient(
        base_url="http://testserver",
        api_key="sk-test-token",
        transport=transport,
    )

    try:
        # 1. Health probe
        health = await client.check_health()
        assert health["status"] == "ok"

        # 2. Create session
        created = await client.create_session(title="Remote Test Session", mode="chat")
        assert created.id is not None
        assert created.title == "Remote Test Session"

        # 3. Get session
        fetched = await client.get_session(created.id)
        assert fetched.id == created.id
        assert fetched.mode == "chat"

        # 4. List sessions
        session_list = await client.list_sessions(limit=10)
        assert session_list.total >= 1
        assert any(s.id == created.id for s in session_list.items)

        # 5. Append message
        msg = await client.post_message(created.id, role="user", content="Hello remote server!")
        assert msg.id is not None
        assert msg.content == "Hello remote server!"

        # 6. List messages
        messages = await client.list_messages(created.id)
        assert len(messages) == 1
        assert messages[0].content == "Hello remote server!"

    finally:
        await client.close()


@pytest.mark.asyncio
async def test_remote_client_stream_and_observer(api_test_app):
    """Test RemoteAgentClient SSE streaming and feeding real-time events to RichAgentObserver."""
    transport = ASGITransport(app=api_test_app)
    client = RemoteAgentClient(
        base_url="http://testserver",
        api_key="sk-test-token",
        transport=transport,
    )

    session = await client.create_session(title="Streaming Test", mode="chat")
    observed_tokens: list[str] = []
    observed_events: list[str] = []

    mock_observer = MagicMock(spec=RichAgentObserver)
    mock_observer.on_token = lambda d: observed_tokens.append(d)
    mock_observer.on_turn_start = lambda turn: observed_events.append(f"turn:{turn}")
    mock_observer.on_tool_start = lambda tc: observed_events.append(f"tool_start:{tc.name}")
    mock_observer.on_tool_end = lambda tr: observed_events.append(f"tool_end:{tr.name}")

    try:
        run_result: RemoteRunResult = await client.execute_remote_run(
            prompt="Compute the results",
            session_id=session.id,
            provider="mock",
            observer=mock_observer,
        )

        assert run_result.status == "succeeded"
        assert run_result.finish_reason == "stop"
        assert "Remote " in run_result.content
        assert "".join(observed_tokens) == run_result.content
        assert any("turn:1" in ev for ev in observed_events)
        assert any("tool_start:search" in ev for ev in observed_events)
        assert any("tool_end:search" in ev for ev in observed_events)
    finally:
        await client.close()


# ============================================================================
# Remote Execution Parity Tests (icarus run and icarus chat)
# ============================================================================


def test_execute_run_remote_parity(api_test_app, test_env):
    """Verify execute_run streams tokens and prints summary panel when remote client is used."""
    transport = ASGITransport(app=api_test_app)
    client = RemoteAgentClient(
        base_url="http://testserver",
        api_key="sk-test-token",
        transport=transport,
    )

    import io

    stdout_buf = io.StringIO()
    console = Console(record=True, width=120)
    exit_code = execute_run(
        prompt="Execute remote calculation",
        provider_name="mock",
        remote=True,
        client=client,
        console=console,
        stdout=stdout_buf,
    )

    assert exit_code == 0
    output = console.export_text()
    streamed_text = stdout_buf.getvalue()
    assert "Remote execution stream works!" in streamed_text
    assert "Run Summary" in output
    assert "Tokens:" in output


def test_execute_run_remote_no_active_server_error(test_env):
    """Verify execute_run with --remote fails gracefully if no server profile is configured."""
    console = Console(record=True)
    exit_code = execute_run(
        prompt="Hello without server",
        remote=True,
        console=console,
    )
    assert exit_code == 1
    output = console.export_text()
    assert "No remote server profile is active" in output


def test_run_chat_remote_parity(api_test_app, test_env):
    """Verify run_chat creates remote session, renders banners, and handles commands."""
    transport = ASGITransport(app=api_test_app)
    client = RemoteAgentClient(
        base_url="http://testserver",
        api_key="sk-test-token",
        transport=transport,
    )

    console = Console(record=True, width=120)

    # Provide inputs: "/session", "What is the time?", "/exit"
    simulated_inputs = iter(["/session", "What is the time?", "/exit"])
    with patch.object(console, "input", side_effect=lambda _: next(simulated_inputs)):
        run_chat(
            provider_name="mock",
            remote=True,
            client=client,
            console=console,
        )

    output = console.export_text()
    assert "Icarus Interactive Chat (Remote:" in output
    assert "Active Remote Session Details" in output
    assert "Remote execution stream works!" in output
    assert "Exiting chat session" in output


def test_sessions_cmd_remote_parity(api_test_app, test_env):
    """Verify icarus sessions --remote queries remote sessions and renders Rich table."""
    transport = ASGITransport(app=api_test_app)
    client = RemoteAgentClient(
        base_url="http://testserver",
        api_key="sk-test-token",
        transport=transport,
    )

    # Pre-create a remote session
    import asyncio

    asyncio.run(client.create_session(title="Remote Session 42", mode="chat"))

    cfg_mgr, _ = test_env
    cfg_mgr.add_server("testserver", "http://testserver", api_key="sk-test-token", active=True)

    with patch("icarus_cli.main.RemoteAgentClient", return_value=client):
        result = runner.invoke(cli_app, ["sessions", "--remote"])
        assert result.exit_code == 0
        assert "Icarus Conversation Sessions" in result.stdout
        assert "Remote Session 42" in result.stdout
