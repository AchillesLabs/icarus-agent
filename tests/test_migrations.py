"""Tests for Alembic automatic migrations and MigrationRunner."""

from datetime import UTC, datetime
from pathlib import Path

from icarus_contracts import (
    MessageCreate,
    MessageRole,
    ScheduledJobCreate,
    ScheduledJobStatus,
    SessionCreate,
)
from icarus_core.persistence.database import DatabaseManager
from icarus_core.persistence.migrations.runner import MigrationRunner
from icarus_core.persistence.repository import (
    MessageRepository,
    ScheduledJobRepository,
    SessionRepository,
)
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
    assert {
        "sessions",
        "messages",
        "agent_runs",
        "scheduled_jobs",
        "tenant_api_tokens",
        "alembic_version",
    }.issubset(table_names)

    # Verify scheduled_jobs columns
    job_columns = {col["name"] for col in inspector.get_columns("scheduled_jobs")}
    expected_columns = {
        "id",
        "owner_id",
        "job_type",
        "scheduled_at",
        "status",
        "payload",
        "claimed_by",
        "claimed_at",
        "completed_at",
        "error_message",
        "retry_count",
        "created_at",
        "updated_at",
    }
    assert expected_columns.issubset(job_columns)

    # Verify tenant_api_tokens columns
    token_columns = {col["name"] for col in inspector.get_columns("tenant_api_tokens")}
    expected_token_columns = {
        "id",
        "owner_id",
        "name",
        "token_hash",
        "prefix",
        "created_at",
        "expires_at",
        "revoked_at",
        "last_used_at",
    }
    assert expected_token_columns.issubset(token_columns)

    # Verify repositories work on migrated schema
    session_repo = SessionRepository(db_manager)
    message_repo = MessageRepository(db_manager)
    job_repo = ScheduledJobRepository(db_manager)
    from icarus_core.persistence import ApiTokenRepository

    token_repo = ApiTokenRepository(db_manager)

    sess = session_repo.create_session(SessionCreate(title="Migrated DB Chat"))
    msg = message_repo.create_message(
        MessageCreate(session_id=sess.id, role=MessageRole.USER, content="Alembic works!")
    )
    job = job_repo.create_job(
        ScheduledJobCreate(job_type="reminder", scheduled_at=datetime.now(UTC))
    )
    tkn = token_repo.create_token(
        owner_id="migrated-tenant",
        name="CI Token",
        token_hash="fakehash123",
        prefix="sk_icarus_...1234",
    )

    retrieved = session_repo.get_session(sess.id)
    assert retrieved is not None
    assert retrieved.title == "Migrated DB Chat"
    messages = message_repo.list_messages(sess.id)
    assert len(messages) == 1
    assert messages[0].id == msg.id
    retrieved_job = job_repo.get_job(job.id)
    assert retrieved_job is not None
    assert retrieved_job.status == ScheduledJobStatus.PENDING
    retrieved_tkn = token_repo.get_token_by_id(tkn.id)
    assert retrieved_tkn is not None
    assert retrieved_tkn.name == "CI Token"
    assert retrieved_tkn.is_active is True


def test_migration_runner_on_memory_db():
    db_manager = DatabaseManager(db_url="sqlite:///:memory:")
    runner = MigrationRunner()

    runner.run_migrations(db_manager=db_manager)
    assert runner.is_migration_up_to_date(db_manager=db_manager) is True

    inspector = inspect(db_manager.engine)
    table_names = set(inspector.get_table_names())
    assert {
        "sessions",
        "messages",
        "agent_runs",
        "scheduled_jobs",
        "tenant_api_tokens",
        "alembic_version",
    }.issubset(table_names)
