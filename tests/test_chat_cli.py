"""Tests for `icarus chat` CLI REPL, session lifecycle, slash commands, and error handling."""

from pathlib import Path
from unittest.mock import patch

from icarus_cli.main import app
from icarus_core.persistence.database import DatabaseManager
from icarus_core.persistence.repository import MessageRepository, SessionRepository
from typer.testing import CliRunner

runner = CliRunner()


def test_chat_starts_new_session_and_exits_cleanly(tmp_path: Path):
    """Launching `icarus chat` creates a new session in SQLite and exits cleanly on /exit."""
    db_file = tmp_path / "icarus.db"
    with (
        patch("icarus_core.paths.get_icarus_home", return_value=tmp_path),
        patch("icarus_core.paths.get_icarus_db_path", return_value=db_file),
    ):
        result = runner.invoke(app, ["chat", "--provider", "mock"], input="/exit\n")
        assert result.exit_code == 0, (
            f"Expected 0 exit code, got {result.exit_code}: {result.stdout}"
        )
        assert "Icarus Chat" in result.stdout or "Session" in result.stdout
        assert (
            "Goodbye" in result.stdout
            or "Exiting" in result.stdout
            or "exit" in result.stdout.lower()
        )

        # Verify session was created in SQLite
        db_mgr = DatabaseManager(db_url=f"sqlite:///{db_file.as_posix()}")
        session_repo = SessionRepository(db_mgr)
        sessions = session_repo.list_sessions()
        assert len(sessions) == 1
        assert sessions[0].mode == "chat"


def test_chat_multi_turn_streaming_and_persistence(tmp_path: Path):
    """User prompt streams assistant response and saves conversation messages to SQLite."""
    db_file = tmp_path / "icarus.db"
    chat_input = "Hello agent\nWhat is your purpose?\n/exit\n"

    with (
        patch("icarus_core.paths.get_icarus_home", return_value=tmp_path),
        patch("icarus_core.paths.get_icarus_db_path", return_value=db_file),
    ):
        result = runner.invoke(app, ["chat", "--provider", "mock"], input=chat_input)
        assert result.exit_code == 0, f"Chat exited with {result.exit_code}: {result.stdout}"
        assert "Mock response from Icarus agent." in result.stdout

        # Verify messages persisted in SQLite
        db_mgr = DatabaseManager(db_url=f"sqlite:///{db_file.as_posix()}")
        session_repo = SessionRepository(db_mgr)
        message_repo = MessageRepository(db_mgr)

        sessions = session_repo.list_sessions()
        assert len(sessions) == 1
        session_id = sessions[0].id

        messages = message_repo.list_messages(session_id)
        assert len(messages) == 4
        assert messages[0].role == "user"
        assert messages[0].content == "Hello agent"
        assert messages[1].role == "assistant"
        assert "Mock response from Icarus agent." in messages[1].content
        assert messages[2].role == "user"
        assert messages[2].content == "What is your purpose?"
        assert messages[3].role == "assistant"


def test_chat_resume_latest_session(tmp_path: Path):
    """Running chat with --resume loads the most recent session and resumes it."""
    db_file = tmp_path / "icarus.db"

    with (
        patch("icarus_core.paths.get_icarus_home", return_value=tmp_path),
        patch("icarus_core.paths.get_icarus_db_path", return_value=db_file),
    ):
        # Turn 1 in original session
        res1 = runner.invoke(
            app, ["chat", "--provider", "mock"], input="Message from first turn\n/exit\n"
        )
        assert res1.exit_code == 0

        # Turn 2 with --resume
        res2 = runner.invoke(
            app,
            ["chat", "--provider", "mock", "--resume"],
            input="Message from second turn\n/exit\n",
        )
        assert res2.exit_code == 0
        assert "Resumed" in res2.stdout or "Session:" in res2.stdout
        # Assert previous messages are displayed in the terminal upon resume
        assert "Message from first turn" in res2.stdout

        # Verify only 1 session exists and has 4 messages
        db_mgr = DatabaseManager(db_url=f"sqlite:///{db_file.as_posix()}")
        session_repo = SessionRepository(db_mgr)
        message_repo = MessageRepository(db_mgr)

        sessions = session_repo.list_sessions()
        assert len(sessions) == 1
        messages = message_repo.list_messages(sessions[0].id)
        assert len(messages) == 4
        assert messages[0].content == "Message from first turn"
        assert messages[2].content == "Message from second turn"


def test_chat_specific_session_id_and_not_found(tmp_path: Path):
    """Targeting --session <id> loads specific thread; invalid ID exits with error."""
    db_file = tmp_path / "icarus.db"

    with (
        patch("icarus_core.paths.get_icarus_home", return_value=tmp_path),
        patch("icarus_core.paths.get_icarus_db_path", return_value=db_file),
    ):
        # Create session 1
        res1 = runner.invoke(app, ["chat", "--provider", "mock"], input="Turn S1\n/exit\n")
        assert res1.exit_code == 0

        # Create session 2
        res2 = runner.invoke(app, ["chat", "--provider", "mock"], input="Turn S2\n/exit\n")
        assert res2.exit_code == 0

        db_mgr = DatabaseManager(db_url=f"sqlite:///{db_file.as_posix()}")
        session_repo = SessionRepository(db_mgr)
        message_repo = MessageRepository(db_mgr)
        sessions = session_repo.list_sessions()
        assert len(sessions) == 2
        # sessions[0] is most recently updated (session 2), sessions[1] is session 1
        s1_id = sessions[1].id

        # Target session 1 explicitly with --session
        res3 = runner.invoke(
            app, ["chat", "--provider", "mock", "--session", s1_id], input="Turn S1 part 2\n/exit\n"
        )
        assert res3.exit_code == 0
        assert "Turn S1" in res3.stdout

        s1_msgs = message_repo.list_messages(s1_id)
        assert len(s1_msgs) == 4
        assert s1_msgs[2].content == "Turn S1 part 2"

        # Invalid session ID
        res_invalid = runner.invoke(
            app, ["chat", "--session", "nonexistent-id-999"], input="/exit\n"
        )
        assert res_invalid.exit_code != 0
        assert "not found" in res_invalid.stdout.lower()


def test_chat_resume_when_no_sessions_exist(tmp_path: Path):
    """Running --resume when no sessions exist creates a new session gracefully."""
    db_file = tmp_path / "icarus.db"

    with (
        patch("icarus_core.paths.get_icarus_home", return_value=tmp_path),
        patch("icarus_core.paths.get_icarus_db_path", return_value=db_file),
    ):
        result = runner.invoke(app, ["chat", "--provider", "mock", "--resume"], input="/exit\n")
        assert result.exit_code == 0
        assert "No previous session" in result.stdout or "Session:" in result.stdout

        db_mgr = DatabaseManager(db_url=f"sqlite:///{db_file.as_posix()}")
        sessions = SessionRepository(db_mgr).list_sessions()
        assert len(sessions) == 1


def test_chat_slash_help(tmp_path: Path):
    """In-chat slash command /help displays command directory."""
    with patch("icarus_core.paths.get_icarus_home", return_value=tmp_path):
        result = runner.invoke(app, ["chat", "--provider", "mock"], input="/help\n/exit\n")
        assert result.exit_code == 0
        assert "/help" in result.stdout
        assert "/clear" in result.stdout
        assert "/session" in result.stdout
        assert "/exit" in result.stdout


def test_chat_slash_session(tmp_path: Path):
    """In-chat slash command /session displays active session status and message count."""
    with patch("icarus_core.paths.get_icarus_home", return_value=tmp_path):
        result = runner.invoke(
            app, ["chat", "--provider", "mock"], input="Hello\n/session\n/exit\n"
        )
        assert result.exit_code == 0
        assert "Active Session" in result.stdout or "Session Details" in result.stdout
        assert "Messages" in result.stdout or "messages" in result.stdout


def test_chat_slash_clear(tmp_path: Path):
    """In-chat slash command /clear clears the screen and redisplays session info."""
    with patch("icarus_core.paths.get_icarus_home", return_value=tmp_path):
        result = runner.invoke(app, ["chat", "--provider", "mock"], input="/clear\n/exit\n")
        assert result.exit_code == 0


def test_chat_provider_error_normalization_without_traceback(tmp_path: Path):
    """Provider errors are displayed in friendly panels without stack traces."""
    from icarus_contracts.exceptions import AuthenticationError
    from icarus_core.providers.mock import MockProvider

    # Simulate authentication error on turn 1, then user recovers on turn 2
    failing_provider = MockProvider(
        should_fail=AuthenticationError("API key rejected by xAI", provider="grok")
    )

    with (
        patch("icarus_core.paths.get_icarus_home", return_value=tmp_path),
        patch(
            "icarus_core.providers.registry.ProviderRegistry.get_provider",
            return_value=failing_provider,
        ),
    ):
        result = runner.invoke(app, ["chat", "--provider", "grok"], input="Hello world\n/exit\n")
        assert result.exit_code == 0
        assert "Provider Error" in result.stdout
        assert "AuthenticationError" in result.stdout
        assert "API key rejected by xAI" in result.stdout
        # Ensure no unhandled Python traceback was leaked
        assert "Traceback (most recent call last)" not in result.stdout


def test_chat_provider_rate_limit_normalization(tmp_path: Path):
    """RateLimitError is handled cleanly without exiting the REPL."""
    from icarus_contracts.exceptions import RateLimitError
    from icarus_core.providers.mock import MockProvider

    failing_provider = MockProvider(
        should_fail=RateLimitError("Rate limit exceeded. Please wait 10s.", provider="grok")
    )

    with (
        patch("icarus_core.paths.get_icarus_home", return_value=tmp_path),
        patch(
            "icarus_core.providers.registry.ProviderRegistry.get_provider",
            return_value=failing_provider,
        ),
    ):
        result = runner.invoke(
            app, ["chat", "--provider", "grok"], input="Generate response\n/exit\n"
        )
        assert result.exit_code == 0
        assert "RateLimitError" in result.stdout
        assert "Rate limit exceeded" in result.stdout
        assert "Traceback (most recent call last)" not in result.stdout


def test_chat_sigint_during_streaming_graceful_recovery(tmp_path: Path):
    """SIGINT during streaming cancels stream without crashing REPL or corrupting DB."""
    from collections.abc import AsyncIterator

    from icarus_contracts.provider import ProviderCapabilities, StreamChunk
    from icarus_core.providers.base import ModelProvider

    class InterruptingProvider(ModelProvider):
        def __init__(self):
            self.turn_count = 0

        async def generate(self, messages, model=None, temperature=0.7, max_tokens=None):
            return None  # not used in chat

        async def stream(
            self, messages, model=None, temperature=0.7, max_tokens=None
        ) -> AsyncIterator[StreamChunk]:
            self.turn_count += 1
            if self.turn_count == 1:
                yield StreamChunk(delta="First token... ")
                # Simulate Ctrl+C raised while reading next token
                raise KeyboardInterrupt()
            else:
                yield StreamChunk(delta="Recovered answer after interrupt.")

        def get_capabilities(self, model=None):
            return ProviderCapabilities()

    interrupting_provider = InterruptingProvider()
    db_file = tmp_path / "icarus.db"

    with (
        patch("icarus_core.paths.get_icarus_home", return_value=tmp_path),
        patch("icarus_core.paths.get_icarus_db_path", return_value=db_file),
        patch(
            "icarus_core.providers.registry.ProviderRegistry.get_provider",
            return_value=interrupting_provider,
        ),
    ):
        # Turn 1 gets interrupted, Turn 2 completes, then /exit
        chat_input = "Interrupt me\nTry again\n/exit\n"
        result = runner.invoke(app, ["chat", "--provider", "mock"], input=chat_input)
        assert result.exit_code == 0
        assert "interrupted by user" in result.stdout.lower()
        assert "Recovered answer after interrupt." in result.stdout

        # Verify DB is intact and messages persisted for both turns
        db_mgr = DatabaseManager(db_url=f"sqlite:///{db_file.as_posix()}")
        session_repo = SessionRepository(db_mgr)
        message_repo = MessageRepository(db_mgr)
        sessions = session_repo.list_sessions()
        assert len(sessions) == 1
        messages = message_repo.list_messages(sessions[0].id)
        # Turn 1 user message was persisted
        assert messages[0].content == "Interrupt me"
        # Turn 2 user and assistant messages were persisted
        assert any(m.content == "Try again" for m in messages)
        assert any("Recovered answer after interrupt." in m.content for m in messages)


def test_chat_with_openrouter_provider(tmp_path: Path):
    """Running chat with --provider openrouter streams model response cleanly."""
    import httpx
    db_file = tmp_path / "icarus.db"

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer sk-or-chat-test"
        sse_body = (
            'data: {"choices":[{"delta":{"content":"Claude "},"finish_reason":null}]}\n\n'
            'data: {"choices":[{"delta":{"content":"speaks!"},"finish_reason":null}]}\n\n'
            'data: {"choices":[{"delta":{"content":""},"finish_reason":"stop"}]}\n\n'
            "data: [DONE]\n\n"
        )
        return httpx.Response(200, text=sse_body, headers={"Content-Type": "text/event-stream"})

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    with (
        patch("icarus_core.paths.get_icarus_home", return_value=tmp_path),
        patch("icarus_core.paths.get_icarus_db_path", return_value=db_file),
        patch("keyring.get_password", return_value="sk-or-chat-test"),
        patch(
            "icarus_core.providers.openrouter.OpenRouterProvider._get_client",
            return_value=mock_client,
        ),
    ):
        result = runner.invoke(app, ["chat", "--provider", "openrouter"], input="Hello\n/exit\n")
        assert result.exit_code == 0
        assert "Claude speaks!" in result.stdout
