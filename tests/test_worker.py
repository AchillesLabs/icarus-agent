"""Tests for the autonomous background worker daemon and task scheduler."""

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from icarus_contracts import (
    ScheduledJobCreate,
    ScheduledJobStatus,
)
from icarus_core.persistence.database import DatabaseManager
from icarus_core.persistence.models import Base
from icarus_core.persistence.repository import (
    AgentRunRepository,
    MessageRepository,
    ScheduledJobRepository,
    SessionRepository,
)
from icarus_worker.config import WorkerSettings
from icarus_worker.daemon import WorkerDaemon
from icarus_worker.handlers import (
    HandlerRegistry,
    NotificationJobHandler,
)


@pytest.fixture
def db_manager():
    """In-memory database initialized with declarative models."""
    manager = DatabaseManager(db_url="sqlite:///:memory:")
    Base.metadata.create_all(manager.engine)
    yield manager
    manager.close()


@pytest.fixture
def job_repo(db_manager):
    return ScheduledJobRepository(db_manager)


def test_worker_settings_defaults():
    settings = WorkerSettings()
    assert settings.worker_id.startswith("worker-")
    assert settings.poll_interval_seconds == 1.0
    assert settings.poll_max_backoff_seconds == 10.0
    assert settings.lease_duration_seconds == 300
    assert settings.max_retries == 3
    assert settings.default_provider == "mock"


@pytest.mark.asyncio
async def test_worker_daemon_run_once_idle(db_manager):
    daemon = WorkerDaemon(db_manager=db_manager)
    result = await daemon.run_once()
    assert result is None
    assert daemon.jobs_processed == 0


@pytest.mark.asyncio
async def test_worker_notification_handler_dispatch(db_manager, job_repo):
    delivered_payloads = []

    def _on_delivery(result):
        delivered_payloads.append(result)

    registry = HandlerRegistry()
    registry.register("reminder", NotificationJobHandler(delivery_callback=_on_delivery))

    daemon = WorkerDaemon(
        db_manager=db_manager,
        handler_registry=registry,
        settings=WorkerSettings(worker_id="test-worker-1"),
    )

    now = datetime.now(UTC)
    job = job_repo.create_job(
        ScheduledJobCreate(
            job_type="reminder",
            scheduled_at=now - timedelta(seconds=1),
            payload={"message": "Drink water!", "channel": "slack"},
            owner_id="tenant-alpha",
        )
    )

    processed = await daemon.run_once()
    assert processed is not None
    assert processed.id == job.id
    assert processed.status == ScheduledJobStatus.COMPLETED
    assert processed.completed_at is not None
    assert daemon.jobs_processed == 1
    assert len(delivered_payloads) == 1
    assert delivered_payloads[0]["message"] == "Drink water!"
    assert delivered_payloads[0]["channel"] == "slack"

    # Verify result recorded in payload
    refreshed = job_repo.get_job(job.id, owner_id="tenant-alpha")
    assert refreshed is not None
    assert refreshed.payload["result"]["status"] == "delivered"


@pytest.mark.asyncio
async def test_worker_agent_run_handler_execution(db_manager, job_repo):
    daemon = WorkerDaemon(
        db_manager=db_manager,
        settings=WorkerSettings(
            worker_id="test-worker-agent",
            default_provider="mock",
            default_model="mock-model",
        ),
    )

    now = datetime.now(UTC)
    job = job_repo.create_job(
        ScheduledJobCreate(
            job_type="agent_run",
            scheduled_at=now - timedelta(seconds=1),
            payload={
                "prompt": "Hello background assistant!",
                "provider": "mock",
                "model": "mock-model",
            },
            owner_id="tenant-beta",
        )
    )

    processed = await daemon.run_once()
    assert processed is not None
    assert processed.id == job.id
    assert processed.status == ScheduledJobStatus.COMPLETED
    assert daemon.jobs_processed == 1

    # Verify session, message, and agent_run were persisted
    session_repo = SessionRepository(db_manager)
    message_repo = MessageRepository(db_manager)
    run_repo = AgentRunRepository(db_manager)

    sessions = session_repo.list_sessions(owner_id="tenant-beta")
    assert len(sessions) == 1
    session_id = sessions[0].id

    messages = message_repo.list_messages(session_id, owner_id="tenant-beta")
    assert len(messages) >= 2  # At least user prompt and assistant response
    assert messages[0].content == "Hello background assistant!"

    runs = run_repo.list_runs_for_session(session_id, owner_id="tenant-beta")
    assert len(runs) == 1
    assert runs[0].status == "succeeded"
    assert runs[0].completed_at is not None


@pytest.mark.asyncio
async def test_worker_unregistered_handler_fails_without_retry(db_manager, job_repo):
    registry = HandlerRegistry()  # Empty registry
    daemon = WorkerDaemon(db_manager=db_manager, handler_registry=registry)

    now = datetime.now(UTC)
    job = job_repo.create_job(
        ScheduledJobCreate(
            job_type="unknown_task_type",
            scheduled_at=now - timedelta(seconds=1),
        ),
        owner_id="tenant-1",
    )

    processed = await daemon.run_once()
    assert processed is not None
    assert processed.id == job.id
    assert processed.status == ScheduledJobStatus.FAILED
    assert "No handler registered" in (processed.error_message or "")
    assert daemon.jobs_failed == 1
    assert daemon.jobs_retried == 0


@pytest.mark.asyncio
async def test_worker_handler_retry_and_exponential_backoff(db_manager, job_repo):
    class FlakyHandler:
        def __init__(self):
            self.attempts = 0

        async def handle(self, job, context):
            self.attempts += 1
            raise RuntimeError(f"Simulated network timeout (attempt {self.attempts})")

    flaky = FlakyHandler()
    registry = HandlerRegistry()
    registry.register("flaky_job", flaky)

    daemon = WorkerDaemon(
        db_manager=db_manager,
        handler_registry=registry,
        settings=WorkerSettings(
            max_retries=2,
            retry_backoff_base_seconds=10,
        ),
    )

    now = datetime.now(UTC)
    job = job_repo.create_job(
        ScheduledJobCreate(
            job_type="flaky_job",
            scheduled_at=now - timedelta(seconds=1),
        ),
        owner_id="tenant-1",
    )

    # Attempt 1: Should fail with retry=True -> pending with retry_count=1
    first_attempt = await daemon.run_once()
    assert first_attempt is not None
    assert first_attempt.status == ScheduledJobStatus.PENDING
    assert first_attempt.retry_count == 1
    assert "Simulated network timeout (attempt 1)" in first_attempt.error_message
    assert daemon.jobs_retried == 1

    # Reset scheduled_at to past so it can be claimed again
    job_repo.update_job(job.id, scheduled_at=now - timedelta(seconds=1), owner_id="tenant-1")

    # Attempt 2: Reaches max_retries=2 -> marked as failed (no more retries)
    second_attempt = await daemon.run_once()
    assert second_attempt is not None
    assert second_attempt.status == ScheduledJobStatus.FAILED
    assert second_attempt.retry_count == 1
    assert daemon.jobs_failed == 1


@pytest.mark.asyncio
async def test_worker_lease_expiration_and_recovery(db_manager, job_repo):
    now = datetime.now(UTC)
    past_time = now - timedelta(minutes=10)

    job = job_repo.create_job(
        ScheduledJobCreate(
            job_type="reminder",
            scheduled_at=past_time,
            payload={"message": "Important task"},
        ),
        owner_id="tenant-1",
    )

    # Worker 1 claims job with 5-minute lease, then crashes without completing
    claimed_job = job_repo.claim_next_job(
        worker_id="worker-crashed",
        lease_duration_seconds=300,
        now=past_time,
    )
    assert claimed_job is not None
    assert claimed_job.status == ScheduledJobStatus.CLAIMED

    # Recovery worker runs now (10 minutes after past_time)
    recovery_worker = WorkerDaemon(
        db_manager=db_manager,
        settings=WorkerSettings(worker_id="worker-recovery", lease_duration_seconds=300),
    )

    recovered = await recovery_worker.run_once()
    assert recovered is not None
    assert recovered.id == job.id
    assert recovered.status == ScheduledJobStatus.COMPLETED
    assert recovery_worker.jobs_processed == 1


@pytest.mark.asyncio
async def test_worker_concurrency_no_double_execution(db_manager, job_repo):
    now = datetime.now(UTC)
    total_jobs = 10
    created_ids = []
    for i in range(total_jobs):
        j = job_repo.create_job(
            ScheduledJobCreate(
                job_type="reminder",
                scheduled_at=now - timedelta(seconds=10 - i),
                payload={"index": i},
            ),
            owner_id="tenant-concurrent",
        )
        created_ids.append(j.id)

    # Create 5 worker daemons competing for the 10 jobs
    workers = [
        WorkerDaemon(
            db_manager=db_manager,
            settings=WorkerSettings(worker_id=f"concurrent-worker-{i}"),
        )
        for i in range(5)
    ]

    async def worker_loop(w: WorkerDaemon):
        # Each worker attempts to claim and process until no jobs remain
        while True:
            res = await w.run_once()
            if res is None:
                break
            await asyncio.sleep(0.01)

    # Run all workers concurrently
    await asyncio.gather(*(worker_loop(w) for w in workers))

    # Verify that all 10 jobs are completed
    jobs = job_repo.list_jobs(owner_id="tenant-concurrent", limit=100)
    assert len(jobs) == total_jobs
    assert all(j.status == ScheduledJobStatus.COMPLETED for j in jobs)

    # Sum of jobs processed across workers must equal total_jobs
    total_processed = sum(w.jobs_processed for w in workers)
    assert total_processed == total_jobs


@pytest.mark.asyncio
async def test_worker_daemon_run_forever_and_stop(db_manager, job_repo):
    daemon = WorkerDaemon(
        db_manager=db_manager,
        settings=WorkerSettings(
            poll_interval_seconds=0.05,
            poll_max_backoff_seconds=0.1,
        ),
    )

    now = datetime.now(UTC)
    job = job_repo.create_job(
        ScheduledJobCreate(
            job_type="reminder",
            scheduled_at=now - timedelta(seconds=1),
            payload={"message": "Periodic reminder"},
        ),
        owner_id="tenant-daemon",
    )

    # Launch daemon in background task
    task = asyncio.create_task(daemon.run_forever())
    # Give time for daemon to claim and complete the job
    await asyncio.sleep(0.15)

    daemon.stop()
    await task

    assert daemon.is_running is False
    assert daemon.jobs_processed == 1
    completed_job = job_repo.get_job(job.id, owner_id="tenant-daemon")
    assert completed_job is not None
    assert completed_job.status == ScheduledJobStatus.COMPLETED
