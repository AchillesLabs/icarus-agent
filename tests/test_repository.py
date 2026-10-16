"""Tests for SessionRepository, MessageRepository, and AgentRunRepository."""

from pathlib import Path

import pytest
from icarus_contracts import (
    MessageCreate,
    MessageRole,
    RunCreate,
    RunStatus,
    SessionCreate,
    SessionUpdate,
)
from icarus_core.persistence.database import DatabaseManager
from icarus_core.persistence.models import Base
from icarus_core.persistence.repository import (
    AgentRunRepository,
    MessageRepository,
    SessionRepository,
)


@pytest.fixture
def in_memory_db() -> DatabaseManager:
    manager = DatabaseManager(db_url="sqlite:///:memory:")
    # Initialize schema for repository tests
    Base.metadata.create_all(manager.engine)
    return manager


@pytest.fixture
def file_based_db(tmp_path: Path) -> DatabaseManager:
    db_file = tmp_path / "test_repo.db"
    manager = DatabaseManager(db_url=f"sqlite:///{db_file.as_posix()}")
    Base.metadata.create_all(manager.engine)
    return manager


def test_session_crud_lifecycle(in_memory_db: DatabaseManager):
    repo = SessionRepository(in_memory_db)

    # 1. Create session
    created = repo.create_session(
        SessionCreate(title="Test Thread", mode="chat", owner_id="user-1")
    )
    assert created.id is not None
    assert created.title == "Test Thread"
    assert created.owner_id == "user-1"
    assert created.metadata_version == 1

    # 2. Get session
    retrieved = repo.get_session(created.id, owner_id="user-1")
    assert retrieved is not None
    assert retrieved.id == created.id
    assert retrieved.title == "Test Thread"

    # 3. Update session
    updated = repo.update_session(
        created.id,
        SessionUpdate(title="Renamed Thread", metadata_version=2),
        owner_id="user-1",
    )
    assert updated is not None
    assert updated.title == "Renamed Thread"
    assert updated.metadata_version == 2

    # 4. Delete session
    assert repo.delete_session(created.id, owner_id="user-1") is True
    assert repo.get_session(created.id, owner_id="user-1") is None


def test_session_owner_isolation(in_memory_db: DatabaseManager):
    repo = SessionRepository(in_memory_db)
    s1 = repo.create_session(SessionCreate(title="User A Session", owner_id="user-a"))
    s2 = repo.create_session(SessionCreate(title="User B Session", owner_id="user-b"))

    # User A cannot read User B's session
    assert repo.get_session(s2.id, owner_id="user-a") is None
    # User B cannot read User A's session
    assert repo.get_session(s1.id, owner_id="user-b") is None

    # Listing is isolated
    sessions_a = repo.list_sessions(owner_id="user-a")
    assert len(sessions_a) == 1
    assert sessions_a[0].id == s1.id

    # Deleting cross-owner fails
    assert repo.delete_session(s2.id, owner_id="user-a") is False
    assert repo.get_session(s2.id, owner_id="user-b") is not None


def test_get_latest_session(in_memory_db: DatabaseManager):
    import time

    repo = SessionRepository(in_memory_db)
    assert repo.get_latest_session(owner_id="user-1") is None

    repo.create_session(SessionCreate(title="Session 1", owner_id="user-1"))
    time.sleep(0.02)
    s2 = repo.create_session(SessionCreate(title="Session 2", owner_id="user-1"))

    latest = repo.get_latest_session(owner_id="user-1")
    assert latest is not None
    assert latest.id == s2.id


def test_message_lifecycle_and_ordering(in_memory_db: DatabaseManager):
    session_repo = SessionRepository(in_memory_db)
    message_repo = MessageRepository(in_memory_db)

    sess = session_repo.create_session(SessionCreate(title="Chat Session", owner_id="user-1"))

    m1 = message_repo.create_message(
        MessageCreate(
            session_id=sess.id,
            role=MessageRole.USER,
            content="Hello",
            token_estimate=2,
            owner_id="user-1",
        )
    )
    m2 = message_repo.create_message(
        MessageCreate(
            session_id=sess.id,
            role=MessageRole.ASSISTANT,
            content="Hi there! How can I help?",
            token_estimate=8,
            owner_id="user-1",
        )
    )

    messages = message_repo.list_messages(sess.id, owner_id="user-1")
    assert len(messages) == 2
    assert messages[0].id == m1.id
    assert messages[0].role == MessageRole.USER
    assert messages[1].id == m2.id
    assert messages[1].role == MessageRole.ASSISTANT

    # Owner isolation for messages
    assert len(message_repo.list_messages(sess.id, owner_id="user-other")) == 0


def test_cascade_delete_session_removes_messages_and_runs(in_memory_db: DatabaseManager):
    session_repo = SessionRepository(in_memory_db)
    message_repo = MessageRepository(in_memory_db)
    run_repo = AgentRunRepository(in_memory_db)

    sess = session_repo.create_session(SessionCreate(title="Parent Session", owner_id="user-1"))
    m1 = message_repo.create_message(
        MessageCreate(session_id=sess.id, role=MessageRole.USER, content="Hello", owner_id="user-1")
    )
    r1 = run_repo.create_run(
        RunCreate(session_id=sess.id, provider="grok", model="grok-2", owner_id="user-1")
    )

    assert message_repo.get_message(m1.id, owner_id="user-1") is not None
    assert run_repo.get_run(r1.id, owner_id="user-1") is not None

    # Deleting session should cascade to messages and runs
    assert session_repo.delete_session(sess.id, owner_id="user-1") is True
    assert message_repo.get_message(m1.id, owner_id="user-1") is None
    assert run_repo.get_run(r1.id, owner_id="user-1") is None


def test_agent_run_lifecycle(in_memory_db: DatabaseManager):
    run_repo = AgentRunRepository(in_memory_db)
    run = run_repo.create_run(
        RunCreate(
            session_id=None,
            owner_id="user-1",
            status=RunStatus.QUEUED,
            provider="grok",
            model="grok-2",
            budget_counters={"max_turns": 10},
            idempotency_key="idemp-123",
        )
    )
    assert run.id is not None
    assert run.status == RunStatus.QUEUED
    assert run.idempotency_key == "idemp-123"

    # Update status to running then succeeded
    updated = run_repo.update_run(
        run.id,
        status=RunStatus.RUNNING,
        owner_id="user-1",
    )
    assert updated is not None
    assert updated.status == RunStatus.RUNNING
    assert updated.started_at is not None

    completed = run_repo.update_run(
        run.id,
        status=RunStatus.SUCCEEDED,
        completed=True,
        owner_id="user-1",
    )
    assert completed is not None
    assert completed.status == RunStatus.SUCCEEDED
    assert completed.completed_at is not None


def test_file_based_sqlite_engine(file_based_db: DatabaseManager):
    session_repo = SessionRepository(file_based_db)
    message_repo = MessageRepository(file_based_db)

    sess = session_repo.create_session(SessionCreate(title="Persistent File Session"))
    msg = message_repo.create_message(
        MessageCreate(session_id=sess.id, role="user", content="Testing on disk")
    )

    assert msg.id is not None
    assert session_repo.get_session(sess.id) is not None
    assert len(message_repo.list_messages(sess.id)) == 1
