"""Tests for session resumption with prior tool history, message reconstruction,
and CLI integration."""

import io
from pathlib import Path
from unittest.mock import patch

import pytest
from icarus_cli.chat import ChatSessionManager
from icarus_cli.run import execute_run
from icarus_contracts.provider import StreamChunk
from icarus_contracts.session import (
    MessageRole,
    RunStatus,
)
from icarus_contracts.tools import ToolCall, ToolDefinition, ToolResult
from icarus_core.agent.loop import AgentLoop
from icarus_core.persistence.database import DatabaseManager
from icarus_core.persistence.models import Base
from icarus_core.persistence.repository import (
    AgentRunRepository,
    MessageRepository,
    SessionRepository,
)
from icarus_core.providers.mock import MockProvider
from icarus_core.tools.base import BaseTool
from icarus_core.tools.registry import ToolRegistry
from rich.console import Console


@pytest.fixture
def test_db_manager(tmp_path: Path) -> DatabaseManager:
    db_file = tmp_path / "test_resumption.db"
    mgr = DatabaseManager(db_url=f"sqlite:///{db_file.as_posix()}")
    Base.metadata.create_all(mgr.engine)
    return mgr


def test_session_resumption_reconstructs_tool_turns(test_db_manager: DatabaseManager):
    """Verify session resumption reconstructs assistant tool calls and tool responses cleanly."""
    session_mgr = ChatSessionManager(db_manager=test_db_manager)
    sess, _ = session_mgr.resolve_session()

    # 1. Turn 1: User asks question
    session_mgr.append_message(sess.id, MessageRole.USER, "List files in repo")

    # 2. Assistant requests tool
    tc = ToolCall(id="call_list_1", name="list_dir", arguments={"path": "."})
    session_mgr.append_message(
        sess.id,
        MessageRole.ASSISTANT,
        content="",
        tool_calls=[tc],
    )

    # 3. Tool responds
    session_mgr.append_message(
        sess.id,
        MessageRole.TOOL,
        content="README.md\npyproject.toml",
        tool_call_id="call_list_1",
        name="list_dir",
    )

    # 4. Assistant replies
    session_mgr.append_message(
        sess.id,
        MessageRole.ASSISTANT,
        content="The files are README.md and pyproject.toml.",
    )

    # Now resume the session as if starting `icarus chat -s <sess.id>`
    resumed_sess, was_resumed = session_mgr.resolve_session(session_id=sess.id)
    assert was_resumed is True
    assert resumed_sess.id == sess.id

    messages = session_mgr.get_messages(sess.id)
    assert len(messages) == 4

    # Reconstruct prompt history for agent loop
    prompt_history = [
        m.to_prompt_message()
        for m in messages
        if (m.role.value if hasattr(m.role, "value") else str(m.role)) != MessageRole.SYSTEM.value
    ]

    assert len(prompt_history) == 4
    # User message
    assert prompt_history[0].role == MessageRole.USER
    assert prompt_history[0].content == "List files in repo"

    # Assistant with tool calls
    assert prompt_history[1].role == MessageRole.ASSISTANT
    assert prompt_history[1].tool_calls is not None
    assert len(prompt_history[1].tool_calls) == 1
    assert prompt_history[1].tool_calls[0].id == "call_list_1"
    assert prompt_history[1].tool_calls[0].name == "list_dir"

    # Tool message
    assert prompt_history[2].role == MessageRole.TOOL
    assert prompt_history[2].tool_call_id == "call_list_1"
    assert prompt_history[2].name == "list_dir"
    assert prompt_history[2].content == "README.md\npyproject.toml"

    # Assistant reply
    assert prompt_history[3].role == MessageRole.ASSISTANT
    assert prompt_history[3].content == "The files are README.md and pyproject.toml."


@pytest.mark.asyncio
async def test_agent_loop_continues_resumed_conversation(test_db_manager: DatabaseManager):
    """Verify AgentLoop receives prior tool history and completes the next turn."""
    session_mgr = ChatSessionManager(db_manager=test_db_manager)
    sess, _ = session_mgr.resolve_session()

    # Pre-populate history with previous tool turn
    session_mgr.append_message(sess.id, MessageRole.USER, "Read pyproject.toml")
    session_mgr.append_message(
        sess.id,
        MessageRole.ASSISTANT,
        content="",
        tool_calls=[ToolCall(id="c1", name="read_file", arguments={"path": "pyproject.toml"})],
    )
    session_mgr.append_message(
        sess.id,
        MessageRole.TOOL,
        content="version = '0.1.0'",
        tool_call_id="c1",
        name="read_file",
    )
    session_mgr.append_message(sess.id, MessageRole.ASSISTANT, content="The version is 0.1.0.")

    # User sends a follow-up message in resumed chat
    session_mgr.append_message(sess.id, MessageRole.USER, "What was the version again?")

    reconstructed_messages = [m.to_prompt_message() for m in session_mgr.get_messages(sess.id)]

    recorded_provider_messages = []
    provider = MockProvider()

    def mock_stream(messages, **kwargs):
        recorded_provider_messages.extend(messages)

        async def gen():
            yield StreamChunk(delta="It is 0.1.0.")

        return gen()

    provider.stream = mock_stream

    agent_loop = AgentLoop(provider=provider, max_turns=5)
    result = await agent_loop.run(messages=reconstructed_messages)

    assert result.content == "It is 0.1.0."
    # Verify that provider was sent all previous tool messages
    roles = [
        m.role.value if hasattr(m.role, "value") else str(m.role)
        for m in recorded_provider_messages
    ]
    assert "tool" in roles
    assert "assistant" in roles
    assert "user" in roles


def test_execute_run_persists_tool_messages_and_counters(tmp_path: Path):
    """Verify execute_run persists all tool messages and sets run budget counters."""
    db_file = tmp_path / "run_persistence.db"
    db_mgr = DatabaseManager(db_url=f"sqlite:///{db_file.as_posix()}")
    Base.metadata.create_all(db_mgr.engine)

    provider = MockProvider()
    turn_counter = 0

    def mock_stream(messages, **kwargs):
        nonlocal turn_counter
        turn_counter += 1

        async def gen():
            if turn_counter == 1:
                yield StreamChunk(
                    delta="",
                    finish_reason="tool_calls",
                    tool_calls=[ToolCall(id="call_list", name="list_dir", arguments={"path": "."})],
                )
            else:
                yield StreamChunk(delta="Found files in directory.")

        return gen()

    provider.stream = mock_stream

    class FakeListTool(BaseTool):
        @property
        def definition(self):
            return ToolDefinition(
                name="list_dir",
                description="list",
                parameters={"type": "object", "properties": {}},
            )

        def execute(self, arguments, workspace_root, call_id="test"):
            return ToolResult(call_id=call_id, name="list_dir", output="file1.txt\nfile2.txt")

    registry = ToolRegistry()
    registry.register(FakeListTool())

    console = Console(record=True)
    stdout = io.StringIO()

    with (
        patch("icarus_cli.run.DatabaseManager", return_value=db_mgr),
        patch("icarus_cli.run.ProviderRegistry.get_provider", return_value=provider),
        patch("icarus_core.tools.registry.create_default_registry", return_value=registry),
    ):
        code = execute_run(
            prompt="List files in repo",
            auto_approve=True,
            console=console,
            stdout=stdout,
        )

    assert code == 0
    message_repo = MessageRepository(db_mgr)
    session_repo = SessionRepository(db_mgr)
    run_repo = AgentRunRepository(db_mgr)

    sessions = session_repo.list_sessions()
    assert len(sessions) == 1
    session_id = sessions[0].id

    messages = message_repo.list_messages(session_id)
    roles = [m.role for m in messages]

    # Verify user message, assistant tool call message, tool response, and final reply
    assert MessageRole.USER in roles
    assert MessageRole.ASSISTANT in roles
    assert MessageRole.TOOL in roles

    tool_msg = next(m for m in messages if m.role == MessageRole.TOOL)
    assert tool_msg.tool_call_id == "call_list"
    assert tool_msg.name == "list_dir"
    assert len(tool_msg.content or "") > 0

    runs = run_repo.list_runs_for_session(session_id)
    assert len(runs) == 1
    assert runs[0].status == RunStatus.SUCCEEDED
    assert runs[0].budget_counters is not None
    assert runs[0].budget_counters.get("turns") == 2
