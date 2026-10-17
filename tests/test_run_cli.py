"""Tests for non-interactive `icarus run` command, stdin piping, and exit codes."""

from pathlib import Path
from unittest.mock import patch

from icarus_cli.main import app
from icarus_contracts.exceptions import AuthenticationError
from icarus_core.persistence.database import DatabaseManager
from icarus_core.persistence.repository import MessageRepository, SessionRepository
from typer.testing import CliRunner

runner = CliRunner()


def test_run_with_argument_prompt_streams_to_stdout_and_exits_0(tmp_path: Path):
    """Passing a prompt argument streams tokens to stdout and exits with code 0."""
    db_file = tmp_path / "icarus.db"
    log_dir = tmp_path / "logs"

    with (
        patch("icarus_core.paths.get_icarus_home", return_value=tmp_path),
        patch("icarus_core.paths.get_icarus_db_path", return_value=db_file),
        patch("icarus_core.paths.get_icarus_logs_dir", return_value=log_dir),
    ):
        result = runner.invoke(app, ["run", "What is the capital of France?", "--provider", "mock"])
        assert result.exit_code == 0, (
            f"Expected 0 exit code, got {result.exit_code}: {result.stdout}"
        )
        assert "Mock response from Icarus agent." in result.stdout

        # Verify session and messages are committed to SQLite
        db_mgr = DatabaseManager(db_url=f"sqlite:///{db_file.as_posix()}")
        session_repo = SessionRepository(db_mgr)
        message_repo = MessageRepository(db_mgr)

        sessions = session_repo.list_sessions()
        assert len(sessions) == 1
        assert sessions[0].mode == "run"

        messages = message_repo.list_messages(sessions[0].id)
        assert len(messages) == 2
        assert messages[0].role == "user"
        assert messages[0].content == "What is the capital of France?"
        assert messages[1].role == "assistant"
        assert "Mock response from Icarus agent." in messages[1].content


def test_run_with_stdin_pipe_streams_to_stdout(tmp_path: Path):
    """Reading from stdin pipe streams output and commits the piped prompt."""
    db_file = tmp_path / "icarus.db"
    log_dir = tmp_path / "logs"
    piped_prompt = "Summarize the text from standard input pipe."

    with (
        patch("icarus_core.paths.get_icarus_home", return_value=tmp_path),
        patch("icarus_core.paths.get_icarus_db_path", return_value=db_file),
        patch("icarus_core.paths.get_icarus_logs_dir", return_value=log_dir),
    ):
        result = runner.invoke(app, ["run", "--provider", "mock"], input=piped_prompt)
        assert result.exit_code == 0, (
            f"Expected 0 exit code, got {result.exit_code}: {result.stdout}"
        )
        assert "Mock response from Icarus agent." in result.stdout

        db_mgr = DatabaseManager(db_url=f"sqlite:///{db_file.as_posix()}")
        message_repo = MessageRepository(db_mgr)
        session_repo = SessionRepository(db_mgr)

        session = session_repo.list_sessions()[0]
        messages = message_repo.list_messages(session.id)
        assert messages[0].content == piped_prompt


def test_run_with_dash_argument_reads_stdin(tmp_path: Path):
    """Explicit '-' prompt argument reads from stdin pipe."""
    db_file = tmp_path / "icarus.db"
    log_dir = tmp_path / "logs"

    with (
        patch("icarus_core.paths.get_icarus_home", return_value=tmp_path),
        patch("icarus_core.paths.get_icarus_db_path", return_value=db_file),
        patch("icarus_core.paths.get_icarus_logs_dir", return_value=log_dir),
    ):
        result = runner.invoke(
            app, ["run", "-", "--provider", "mock"], input="Piped content via dash\n"
        )
        assert result.exit_code == 0
        assert "Mock response from Icarus agent." in result.stdout


def test_run_empty_prompt_and_empty_stdin_exits_1(tmp_path: Path):
    """Running without prompt argument and empty stdin exits with code 1."""
    db_file = tmp_path / "icarus.db"
    log_dir = tmp_path / "logs"

    with (
        patch("icarus_core.paths.get_icarus_home", return_value=tmp_path),
        patch("icarus_core.paths.get_icarus_db_path", return_value=db_file),
        patch("icarus_core.paths.get_icarus_logs_dir", return_value=log_dir),
    ):
        result = runner.invoke(app, ["run", "--provider", "mock"], input="")
        assert result.exit_code == 1
        assert "No prompt provided" in result.stdout or "Error" in result.stdout


def test_run_provider_error_returns_exit_code_1_and_redacts(tmp_path: Path):
    """Provider errors return exit code 1, omit tracebacks, and redact secrets in logs."""
    db_file = tmp_path / "icarus.db"
    log_dir = tmp_path / "logs"

    with (
        patch("icarus_core.paths.get_icarus_home", return_value=tmp_path),
        patch("icarus_core.paths.get_icarus_db_path", return_value=db_file),
        patch("icarus_core.paths.get_icarus_logs_dir", return_value=log_dir),
        patch(
            "icarus_core.providers.mock.MockProvider.stream",
            side_effect=AuthenticationError("Invalid API key xai-secret-1234567890abcdef"),
        ),
    ):
        result = runner.invoke(app, ["run", "Test prompt", "--provider", "mock"])
        assert result.exit_code == 1
        # No raw Python traceback in user-facing output
        assert "Traceback (most recent call last)" not in result.stdout
        assert "AuthenticationError" in result.stdout or "Provider error" in result.stdout
        assert "xai-secret-1234567890abcdef" not in result.stdout
        assert "[REDACTED]" in result.stdout

        # Verify log file has redacted secret
        log_file = log_dir / "cli.log"
        if log_file.exists():
            log_content = log_file.read_text(encoding="utf-8")
            assert "xai-secret-1234567890abcdef" not in log_content
            assert "[REDACTED]" in log_content


def test_run_sigint_returns_exit_code_130(tmp_path: Path):
    """SIGINT / KeyboardInterrupt during generation returns POSIX 130 exit code."""
    db_file = tmp_path / "icarus.db"
    log_dir = tmp_path / "logs"

    with (
        patch("icarus_core.paths.get_icarus_home", return_value=tmp_path),
        patch("icarus_core.paths.get_icarus_db_path", return_value=db_file),
        patch("icarus_core.paths.get_icarus_logs_dir", return_value=log_dir),
        patch(
            "icarus_core.providers.mock.MockProvider.stream",
            side_effect=KeyboardInterrupt(),
        ),
    ):
        result = runner.invoke(app, ["run", "Prompt to cancel", "--provider", "mock"])
        assert result.exit_code == 130


def test_logs_command_when_no_log_file(tmp_path: Path):
    """Running `icarus logs` when no log file exists prints a friendly notice."""
    with patch("icarus_core.paths.get_icarus_home", return_value=tmp_path):
        result = runner.invoke(app, ["logs"])
        assert result.exit_code == 0
        assert "No logs found" in result.stdout


def test_logs_command_displays_records_and_respects_tail(tmp_path: Path):
    """Running `icarus logs` prints lines and --tail limits recent output."""
    log_dir = tmp_path / "logs"
    log_dir.mkdir(parents=True)
    log_file = log_dir / "cli.log"
    log_file.write_text("line 1\nline 2\nline 3\nline 4\nline 5\n", encoding="utf-8")

    with patch("icarus_core.paths.get_icarus_home", return_value=tmp_path):
        result = runner.invoke(app, ["logs", "--tail", "2"])
        assert result.exit_code == 0
        assert "line 4" in result.stdout
        assert "line 5" in result.stdout
        assert "line 1" not in result.stdout


def test_run_with_openrouter_provider_streams_and_commits(tmp_path: Path):
    """Running with --provider openrouter streams tokens and persists session."""
    import httpx

    db_file = tmp_path / "icarus.db"
    log_dir = tmp_path / "logs"

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer sk-or-test-key"
        sse_body = (
            'data: {"choices":[{"delta":{"content":"OpenRouter"},"finish_reason":null}]}\n\n'
            'data: {"choices":[{"delta":{"content":" success"},"finish_reason":null}]}\n\n'
            'data: {"choices":[{"delta":{"content":""},"finish_reason":"stop"}]}\n\n'
            "data: [DONE]\n\n"
        )
        return httpx.Response(200, text=sse_body, headers={"Content-Type": "text/event-stream"})

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    with (
        patch("icarus_core.paths.get_icarus_home", return_value=tmp_path),
        patch("icarus_core.paths.get_icarus_db_path", return_value=db_file),
        patch("icarus_core.paths.get_icarus_logs_dir", return_value=log_dir),
        patch("keyring.get_password", return_value="sk-or-test-key"),
        patch(
            "icarus_core.providers.openrouter.OpenRouterProvider._get_client",
            return_value=mock_client,
        ),
    ):
        result = runner.invoke(
            app,
            [
                "run",
                "Hello OpenRouter",
                "--provider",
                "openrouter",
                "--model",
                "anthropic/claude-3.5-sonnet",
            ],
        )
        assert result.exit_code == 0
        assert "OpenRouter success" in result.stdout

        db_mgr = DatabaseManager(db_url=f"sqlite:///{db_file.as_posix()}")
        session_repo = SessionRepository(db_mgr)
        message_repo = MessageRepository(db_mgr)

        sessions = session_repo.list_sessions()
        assert len(sessions) == 1
        messages = message_repo.list_messages(sessions[0].id)
        assert len(messages) == 2
        assert messages[0].content == "Hello OpenRouter"
        assert messages[1].content == "OpenRouter success"


def test_run_injects_system_prompt_to_provider(tmp_path: Path):
    """icarus run prepends structured system prompt before calling provider."""
    from icarus_contracts.session import MessageRole
    from icarus_core.providers.mock import MockProvider
    from icarus_core.providers.registry import ProviderRegistry

    db_file = tmp_path / "icarus.db"
    log_dir = tmp_path / "logs"
    mock_prov = MockProvider()

    with (
        patch("icarus_core.paths.get_icarus_home", return_value=tmp_path),
        patch("icarus_core.paths.get_icarus_db_path", return_value=db_file),
        patch("icarus_core.paths.get_icarus_logs_dir", return_value=log_dir),
        patch.object(ProviderRegistry, "get_provider", return_value=mock_prov),
    ):
        result = runner.invoke(app, ["run", "What is the capital of France?", "--provider", "mock"])
        assert result.exit_code == 0
        assert len(mock_prov.recorded_prompts) == 1
        sent_messages = mock_prov.recorded_prompts[0]
        assert len(sent_messages) == 2
        assert sent_messages[0].role in (MessageRole.SYSTEM, "system")
        assert "Icarus" in sent_messages[0].content
        assert "Operating System:" in sent_messages[0].content
        assert "Working Directory:" in sent_messages[0].content
        assert sent_messages[1].role in (MessageRole.USER, "user")
        assert sent_messages[1].content == "What is the capital of France?"
