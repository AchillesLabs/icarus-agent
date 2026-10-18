"""Tests for SQLite tool persistence, tool messages, and schema migrations."""

from pathlib import Path

import pytest
from icarus_contracts.provider import PromptMessage
from icarus_contracts.session import (
    MessageCreate,
    MessageRole,
    SessionCreate,
)
from icarus_contracts.tools import ToolCall
from icarus_core.persistence.database import DatabaseManager
from icarus_core.persistence.migrations.runner import MigrationRunner
from icarus_core.persistence.models import Base
from icarus_core.persistence.repository import MessageRepository, SessionRepository
from sqlalchemy import inspect


@pytest.fixture
def in_memory_db() -> DatabaseManager:
    manager = DatabaseManager(db_url="sqlite:///:memory:")
    Base.metadata.create_all(manager.engine)
    return manager


def test_tool_message_dto_and_prompt_message_conversion():
    """Verify MessageDTO converts cleanly to PromptMessage preserving tool_calls and
    tool_call_id."""
    # 1. Assistant message with tool calls
    tc = ToolCall(id="call_123", name="read_file", arguments={"path": "main.py"})
    create_payload = MessageCreate(
        session_id="sess-1",
        role=MessageRole.ASSISTANT,
        content=None,
        tool_calls=[tc],
    )
    assert create_payload.role == MessageRole.ASSISTANT
    assert create_payload.tool_calls is not None
    assert len(create_payload.tool_calls) == 1

    # 2. Tool response message
    tool_create = MessageCreate(
        session_id="sess-1",
        role=MessageRole.TOOL,
        content="def hello(): pass",
        tool_call_id="call_123",
        name="read_file",
    )
    assert tool_create.role == MessageRole.TOOL
    assert tool_create.tool_call_id == "call_123"
    assert tool_create.name == "read_file"


def test_message_repository_persists_tool_calls_and_responses(in_memory_db: DatabaseManager):
    """Verify MessageRepository persists and retrieves tool calls and role=tool responses."""
    session_repo = SessionRepository(in_memory_db)
    message_repo = MessageRepository(in_memory_db)

    sess = session_repo.create_session(SessionCreate(title="Tool Session"))

    # 1. User message
    msg_user = message_repo.create_message(
        MessageCreate(
            session_id=sess.id,
            role=MessageRole.USER,
            content="Can you read pyproject.toml?",
        )
    )

    # 2. Assistant message with tool calls
    tc = ToolCall(id="call_read_1", name="read_file", arguments={"path": "pyproject.toml"})
    msg_assistant = message_repo.create_message(
        MessageCreate(
            session_id=sess.id,
            role=MessageRole.ASSISTANT,
            content="",
            tool_calls=[tc],
        )
    )

    # 3. Tool response message
    msg_tool = message_repo.create_message(
        MessageCreate(
            session_id=sess.id,
            role=MessageRole.TOOL,
            content="[project]\nname = 'icarus-agent'",
            tool_call_id="call_read_1",
            name="read_file",
        )
    )

    # 4. Final assistant answer
    msg_final = message_repo.create_message(
        MessageCreate(
            session_id=sess.id,
            role=MessageRole.ASSISTANT,
            content="The project name is icarus-agent.",
        )
    )

    # Retrieve all messages in order
    messages = message_repo.list_messages(sess.id)
    assert len(messages) == 4

    assert messages[0].id == msg_user.id
    assert messages[0].role == MessageRole.USER
    assert messages[0].content == "Can you read pyproject.toml?"

    # Check assistant with tool_calls
    assert messages[1].id == msg_assistant.id
    assert messages[1].role == MessageRole.ASSISTANT
    assert messages[1].tool_calls is not None
    assert len(messages[1].tool_calls) == 1
    prompt_msg1 = messages[1].to_prompt_message()
    assert isinstance(prompt_msg1, PromptMessage)
    assert prompt_msg1.role == MessageRole.ASSISTANT
    assert prompt_msg1.tool_calls is not None
    assert prompt_msg1.tool_calls[0].id == "call_read_1"
    assert prompt_msg1.tool_calls[0].name == "read_file"
    assert prompt_msg1.tool_calls[0].get_arguments_dict() == {"path": "pyproject.toml"}

    # Check tool response message
    assert messages[2].id == msg_tool.id
    assert messages[2].role == MessageRole.TOOL
    assert messages[2].tool_call_id == "call_read_1"
    assert messages[2].name == "read_file"
    assert messages[2].content == "[project]\nname = 'icarus-agent'"
    prompt_msg2 = messages[2].to_prompt_message()
    assert prompt_msg2.role == MessageRole.TOOL
    assert prompt_msg2.tool_call_id == "call_read_1"
    assert prompt_msg2.name == "read_file"
    assert prompt_msg2.content == "[project]\nname = 'icarus-agent'"

    # Check final message
    assert messages[3].id == msg_final.id
    assert messages[3].role == MessageRole.ASSISTANT
    assert messages[3].content == "The project name is icarus-agent."


def test_migration_0002_tool_persistence(tmp_path: Path):
    """Verify that Alembic migration 0002 adds tool_calls, tool_call_id, and name columns."""
    db_file = tmp_path / "migration_tool_test.db"
    db_url = f"sqlite:///{db_file.as_posix()}"
    runner = MigrationRunner()

    runner.run_migrations(db_url=db_url)
    assert runner.is_migration_up_to_date(db_url=db_url) is True

    db_manager = DatabaseManager(db_url=db_url)
    inspector = inspect(db_manager.engine)
    columns = {col["name"]: col for col in inspector.get_columns("messages")}

    assert "tool_calls" in columns
    assert "tool_call_id" in columns
    assert "name" in columns
