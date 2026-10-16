"""Tests for Alembic automatic migrations and MigrationRunner."""

from pathlib import Path

from icarus_contracts import MessageCreate, MessageRole, SessionCreate
from icarus_core.persistence.database import DatabaseManager
from icarus_core.persistence.migrations.runner import MigrationRunner
from icarus_core.persistence.repository import MessageRepository, SessionRepository
from sqlalchemy import inspect


def test_migration_runner_head_revision():
    runner = MigrationRunner()
    head = runner.get_head_revision()
    assert head is not None
    assert len(head) > 0


def test_migration_runner_on_file_db(tmp_path: Path):
    db_file = tmp_path / "migrated.db"
    db_url = f"sqlite:///{db_file.as_posix()}"
    runner = MigrationRunner()

    # Before migration
    assert runner.is_migration_up_to_date(db_url=db_url) is False
    assert runner.get_current_revision(db_url=db_url) is None

    # Run migration to head
    runner.run_migrations(db_url=db_url)

    # After migration
    assert runner.is_migration_up_to_date(db_url=db_url) is True
    assert runner.get_current_revision(db_url=db_url) == runner.get_head_revision()

    # Verify idempotency
    runner.run_migrations(db_url=db_url)
    assert runner.is_migration_up_to_date(db_url=db_url) is True

    # Verify tables created
    db_manager = DatabaseManager(db_url=db_url)
    inspector = inspect(db_manager.engine)
    table_names = set(inspector.get_table_names())
    assert {"sessions", "messages", "agent_runs", "alembic_version"}.issubset(table_names)

    # Verify repositories work on migrated schema
    session_repo = SessionRepository(db_manager)
    message_repo = MessageRepository(db_manager)

    sess = session_repo.create_session(SessionCreate(title="Migrated DB Chat"))
    msg = message_repo.create_message(
        MessageCreate(session_id=sess.id, role=MessageRole.USER, content="Alembic works!")
    )

    retrieved = session_repo.get_session(sess.id)
    assert retrieved is not None
    assert retrieved.title == "Migrated DB Chat"
    messages = message_repo.list_messages(sess.id)
    assert len(messages) == 1
    assert messages[0].id == msg.id


def test_migration_runner_on_memory_db():
    db_manager = DatabaseManager(db_url="sqlite:///:memory:")
    runner = MigrationRunner()

    runner.run_migrations(db_manager=db_manager)
    assert runner.is_migration_up_to_date(db_manager=db_manager) is True

    inspector = inspect(db_manager.engine)
    table_names = set(inspector.get_table_names())
    assert {"sessions", "messages", "agent_runs", "alembic_version"}.issubset(table_names)
