"""Tests for session management CLI commands (`icarus sessions` and `icarus history`)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from icarus_cli.main import app
from icarus_contracts import MessageCreate, MessageRole, RunCreate, RunStatus, SessionCreate
from icarus_contracts.tools import ToolCall
from icarus_core.persistence.database import DatabaseManager
from icarus_core.persistence.models import Base
from icarus_core.persistence.repository import (
    AgentRunRepository,
    MessageRepository,
    SessionRepository,
)
from typer.testing import CliRunner

runner = CliRunner()


def test_sessions_command_empty_database(tmp_path: Path):
    """Running `icarus sessions` with no sessions prints a friendly notice."""
    db_file = tmp_path / "icarus.db"
    db_mgr = DatabaseManager(db_url=f"sqlite:///{db_file.as_posix()}")
    Base.metadata.create_all(db_mgr.engine)

    with (
        patch("icarus_core.paths.get_icarus_home", return_value=tmp_path),
        patch("icarus_core.paths.get_icarus_db_path", return_value=db_file),
        patch("icarus_cli.main.ensure_database_migrated"),
    ):
        result = runner.invoke(app, ["sessions"])
        assert result.exit_code == 0
        assert "No previous sessions found" in result.stdout or "No sessions found" in result.stdout


def test_sessions_command_lists_sessions_with_telemetry_and_limit(tmp_path: Path):
    """`icarus sessions` displays table with ID, title, mode, message count, and tokens."""
    db_file = tmp_path / "icarus.db"
    db_mgr = DatabaseManager(db_url=f"sqlite:///{db_file.as_posix()}")
    Base.metadata.create_all(db_mgr.engine)

    session_repo = SessionRepository(db_mgr)
    message_repo = MessageRepository(db_mgr)
    run_repo = AgentRunRepository(db_mgr)

    # Session 1: chat mode with 2 messages
    s1 = session_repo.create_session(SessionCreate(title="First Chat Session", mode="chat"))
    message_repo.create_message(
        MessageCreate(
            session_id=s1.id,
            role=MessageRole.USER,
            content="Hello there",
            token_estimate=15,
        )
    )
    message_repo.create_message(
        MessageCreate(
            session_id=s1.id,
            role=MessageRole.ASSISTANT,
            content="General Kenobi",
            token_estimate=25,
        )
    )

    # Session 2: run mode with 1 message and 1 run
    s2 = session_repo.create_session(SessionCreate(title="Automated Task Run", mode="run"))
    message_repo.create_message(
        MessageCreate(
            session_id=s2.id,
            role=MessageRole.USER,
            content="Analyze code",
            token_estimate=40,
        )
    )
    run_repo.create_run(
        RunCreate(
            session_id=s2.id,
            status=RunStatus.SUCCEEDED,
            budget_counters={"total_tokens": 120},
        )
    )

    with (
        patch("icarus_core.paths.get_icarus_home", return_value=tmp_path),
        patch("icarus_core.paths.get_icarus_db_path", return_value=db_file),
        patch("icarus_cli.main.ensure_database_migrated"),
    ):
        # 1. Default invoke
        result = runner.invoke(app, ["sessions"])
        assert result.exit_code == 0
        assert "First Chat Session" in result.stdout
        assert "Automated Task Run" in result.stdout
        assert "chat" in result.stdout
        assert "run" in result.stdout

        # Verify limit flag works
        result_limit = runner.invoke(app, ["sessions", "--limit", "1"])
        assert result_limit.exit_code == 0
        # Only the most recently active session should appear
        assert "Automated Task Run" in result_limit.stdout


def test_history_command_nonexistent_session_exits_1(tmp_path: Path):
    """Running `icarus history <bad_id>` prints an error and exits with code 1."""
    db_file = tmp_path / "icarus.db"
    db_mgr = DatabaseManager(db_url=f"sqlite:///{db_file.as_posix()}")
    Base.metadata.create_all(db_mgr.engine)

    with (
        patch("icarus_core.paths.get_icarus_home", return_value=tmp_path),
        patch("icarus_core.paths.get_icarus_db_path", return_value=db_file),
        patch("icarus_cli.main.ensure_database_migrated"),
    ):
        result = runner.invoke(app, ["history", "nonexistent-session-uuid"])
        assert result.exit_code == 1
        assert "nonexistent-session-uuid" in result.stdout
        assert "not found" in result.stdout.lower()


def test_history_command_renders_formatted_transcript(tmp_path: Path):
    """`icarus history <id>` renders user prompts, assistant replies, tool calls and results."""
    db_file = tmp_path / "icarus.db"
    db_mgr = DatabaseManager(db_url=f"sqlite:///{db_file.as_posix()}")
    Base.metadata.create_all(db_mgr.engine)

    session_repo = SessionRepository(db_mgr)
    message_repo = MessageRepository(db_mgr)

    sess = session_repo.create_session(
        SessionCreate(title="History Transcript Inspection", mode="chat")
    )

    # User message
    message_repo.create_message(
        MessageCreate(
            session_id=sess.id,
            role=MessageRole.USER,
            content="Can you list files in the current directory?",
            token_estimate=12,
        )
    )

    # Assistant tool call message
    tc = ToolCall(id="call_list_99", name="list_dir", arguments={"path": "."})
    message_repo.create_message(
        MessageCreate(
            session_id=sess.id,
            role=MessageRole.ASSISTANT,
            content="Let me check the files for you.",
            tool_calls=[tc],
            token_estimate=28,
        )
    )

    # Tool result message
    message_repo.create_message(
        MessageCreate(
            session_id=sess.id,
            role=MessageRole.TOOL,
            content="README.md\npyproject.toml\nsrc/",
            tool_call_id="call_list_99",
            name="list_dir",
            token_estimate=16,
        )
    )

    # Final assistant reply
    message_repo.create_message(
        MessageCreate(
            session_id=sess.id,
            role=MessageRole.ASSISTANT,
            content="Here are the project files: README.md, pyproject.toml, and src/.",
            token_estimate=22,
        )
    )

    with (
        patch("icarus_core.paths.get_icarus_home", return_value=tmp_path),
        patch("icarus_core.paths.get_icarus_db_path", return_value=db_file),
        patch("icarus_cli.main.ensure_database_migrated"),
    ):
        result = runner.invoke(app, ["history", sess.id])
        assert result.exit_code == 0
        # Header / Title
        assert "History Transcript Inspection" in result.stdout
        # User message
        assert "Can you list files in the current directory?" in result.stdout
        # Assistant message
        assert "Let me check the files for you." in result.stdout
        # Tool call
        assert "list_dir" in result.stdout
        # Tool output
        assert "README.md" in result.stdout
        assert "pyproject.toml" in result.stdout
        # Token indicators
        assert "tokens" in result.stdout.lower()


def test_run_command_displays_telemetry_summary_panel(tmp_path: Path):
    """Running `icarus run` prints a summary telemetry panel upon completion."""
    db_file = tmp_path / "icarus.db"
    log_dir = tmp_path / "logs"

    with (
        patch("icarus_core.paths.get_icarus_home", return_value=tmp_path),
        patch("icarus_core.paths.get_icarus_db_path", return_value=db_file),
        patch("icarus_core.paths.get_icarus_logs_dir", return_value=log_dir),
    ):
        result = runner.invoke(app, ["run", "Hello world telemetry", "--provider", "mock"])
        assert result.exit_code == 0
        assert "Run Summary" in result.stdout or "Summary" in result.stdout
        assert "Turns" in result.stdout
        assert "Tokens" in result.stdout
        assert "Duration" in result.stdout
