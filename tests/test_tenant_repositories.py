"""Tests for tenant-scoped repository isolation in icarus_core.persistence."""

import pytest
from icarus_contracts import (
    MessageCreate,
    MessageRole,
    RunCreate,
    RunStatus,
    SessionCreate,
    SessionUpdate,
    TenantAccessDeniedError,
)
from icarus_core.persistence.database import DatabaseManager
from icarus_core.persistence.models import Base
from icarus_core.persistence.repository import (
    TenantMessageRepository,
    TenantRunRepository,
    TenantSessionRepository,
)


@pytest.fixture
def test_db() -> DatabaseManager:
    manager = DatabaseManager(db_url="sqlite:///:memory:")
    Base.metadata.create_all(manager.engine)
    return manager


def test_tenant_session_repository_strict_isolation(test_db: DatabaseManager):
    repo_alice = TenantSessionRepository(test_db, owner_id="alice")
    repo_bob = TenantSessionRepository(test_db, owner_id="bob")

    # Alice creates a session with malicious owner_id attempt in payload
    session_alice = repo_alice.create_session(
        SessionCreate(title="Alice Confidential", mode="chat", owner_id="bob")
    )
    # The repository must override and enforce Alice's owner_id
    assert session_alice.owner_id == "alice"

    # Alice can fetch it
    assert repo_alice.get_session(session_alice.id) is not None
    assert repo_alice.get_session(session_alice.id).title == "Alice Confidential"

    # Bob cannot fetch Alice's session
    assert repo_bob.get_session(session_alice.id) is None

    # Bob's list does not contain Alice's session
    bob_sessions = repo_bob.list_sessions()
    assert all(s.id != session_alice.id for s in bob_sessions)

    # Bob cannot update Alice's session
    updated = repo_bob.update_session(session_alice.id, SessionUpdate(title="Bob Hacked Alice"))
    assert updated is None

    # Bob cannot delete Alice's session
    deleted = repo_bob.delete_session(session_alice.id)
    assert deleted is False
    assert repo_alice.get_session(session_alice.id) is not None


def test_tenant_message_repository_rejects_cross_tenant_message(test_db: DatabaseManager):
    repo_alice_sess = TenantSessionRepository(test_db, owner_id="alice")
    repo_alice_msg = TenantMessageRepository(test_db, owner_id="alice")
    repo_bob_msg = TenantMessageRepository(test_db, owner_id="bob")

    session_alice = repo_alice_sess.create_session(SessionCreate(title="Alice Thread", mode="chat"))

    # Bob attempts to post a message into Alice's session
    with pytest.raises(TenantAccessDeniedError):
        repo_bob_msg.create_message(
            MessageCreate(
                session_id=session_alice.id,
                role=MessageRole.USER,
                content="Bob injection",
            )
        )

    # Alice can post successfully
    alice_msg = repo_alice_msg.create_message(
        MessageCreate(
            session_id=session_alice.id,
            role=MessageRole.USER,
            content="Alice message",
        )
    )
    assert alice_msg.owner_id == "alice"

    # Bob cannot view Alice's messages
    assert repo_bob_msg.get_message(alice_msg.id) is None
    assert repo_bob_msg.list_messages(session_alice.id) == []


def test_tenant_run_repository_rejects_cross_tenant_run(test_db: DatabaseManager):
    repo_alice_sess = TenantSessionRepository(test_db, owner_id="alice")
    repo_alice_run = TenantRunRepository(test_db, owner_id="alice")
    repo_bob_run = TenantRunRepository(test_db, owner_id="bob")

    session_alice = repo_alice_sess.create_session(SessionCreate(title="Alice Thread", mode="chat"))

    # Bob attempts to start a run in Alice's session
    with pytest.raises(TenantAccessDeniedError):
        repo_bob_run.create_run(
            RunCreate(
                session_id=session_alice.id,
                status=RunStatus.RUNNING,
                provider="grok",
                model="grok-2",
            )
        )

    # Alice can create a run
    alice_run = repo_alice_run.create_run(
        RunCreate(
            session_id=session_alice.id,
            status=RunStatus.RUNNING,
            provider="grok",
            model="grok-2",
        )
    )
    assert alice_run.owner_id == "alice"

    # Bob cannot read or update Alice's run
    assert repo_bob_run.get_run(alice_run.id) is None
    assert repo_bob_run.update_run(alice_run.id, status=RunStatus.CANCELLED) is None
