"""Integration tests for ScheduledJobRepository and ScheduledJobModel."""

from datetime import UTC, datetime, timedelta

import pytest
from icarus_contracts import (
    ScheduledJobCreate,
    ScheduledJobStatus,
    ScheduledJobUpdate,
)
from icarus_core.persistence.database import DatabaseManager
from icarus_core.persistence.models import Base
from icarus_core.persistence.repository import (
    ScheduledJobRepository,
    TenantScheduledJobRepository,
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


def test_create_and_get_scheduled_job(job_repo):
    now = datetime.now(UTC)
    job = job_repo.create_job(
        ScheduledJobCreate(
            job_type="reminder",
            scheduled_at=now,
            payload={"message": "Time to stand up!"},
            owner_id="tenant-alpha",
        )
    )

    assert job.id is not None
    assert job.owner_id == "tenant-alpha"
    assert job.job_type == "reminder"
    assert job.status == ScheduledJobStatus.PENDING
    assert job.payload == {"message": "Time to stand up!"}
    assert job.retry_count == 0
    assert job.claimed_by is None
    assert job.claimed_at is None
    assert job.completed_at is None
    assert job.error_message is None

    # Retrieve
    retrieved = job_repo.get_job(job.id, owner_id="tenant-alpha")
    assert retrieved is not None
    assert retrieved.id == job.id
    assert retrieved.payload == {"message": "Time to stand up!"}

    # Wrong owner returns None
    assert job_repo.get_job(job.id, owner_id="other-tenant") is None
    # Non-existent ID returns None
    assert job_repo.get_job("non-existent-id", owner_id="tenant-alpha") is None


def test_list_jobs_and_filtering(job_repo):
    now = datetime.now(UTC)
    # Create 3 jobs for tenant-1
    j1 = job_repo.create_job(
        ScheduledJobCreate(job_type="email_digest", scheduled_at=now + timedelta(minutes=1)),
        owner_id="tenant-1",
    )
    j2 = job_repo.create_job(
        ScheduledJobCreate(job_type="cleanup", scheduled_at=now + timedelta(minutes=2)),
        owner_id="tenant-1",
    )
    j3 = job_repo.create_job(
        ScheduledJobCreate(job_type="email_digest", scheduled_at=now + timedelta(minutes=3)),
        owner_id="tenant-1",
    )
    # Create 1 job for tenant-2
    job_repo.create_job(
        ScheduledJobCreate(job_type="email_digest", scheduled_at=now),
        owner_id="tenant-2",
    )

    # Mark j2 as completed
    job_repo.update_job(j2.id, completed=True, owner_id="tenant-1")

    # List all for tenant-1
    all_jobs = job_repo.list_jobs(owner_id="tenant-1")
    assert len(all_jobs) == 3
    assert [j.id for j in all_jobs] == [j1.id, j2.id, j3.id]

    # Filter by job_type
    email_jobs = job_repo.list_jobs(owner_id="tenant-1", job_type="email_digest")
    assert len(email_jobs) == 2
    assert [j.id for j in email_jobs] == [j1.id, j3.id]

    # Filter by status
    pending_jobs = job_repo.list_jobs(owner_id="tenant-1", status=ScheduledJobStatus.PENDING)
    assert len(pending_jobs) == 2
    assert [j.id for j in pending_jobs] == [j1.id, j3.id]

    completed_jobs = job_repo.list_jobs(owner_id="tenant-1", status=ScheduledJobStatus.COMPLETED)
    assert len(completed_jobs) == 1
    assert completed_jobs[0].id == j2.id

    # Pagination
    paged = job_repo.list_jobs(owner_id="tenant-1", limit=1, offset=1)
    assert len(paged) == 1
    assert paged[0].id == j2.id


def test_update_job(job_repo):
    now = datetime.now(UTC)
    job = job_repo.create_job(
        ScheduledJobCreate(job_type="webhook", scheduled_at=now),
        owner_id="tenant-1",
    )

    future_time = now + timedelta(hours=1)
    updated = job_repo.update_job(
        job.id,
        update=ScheduledJobUpdate(
            payload={"url": "https://example.com/webhook"},
            error_message="Temporary network glitch",
            retry_count=2,
            scheduled_at=future_time,
        ),
        owner_id="tenant-1",
    )

    assert updated is not None
    assert updated.payload == {"url": "https://example.com/webhook"}
    assert updated.error_message == "Temporary network glitch"
    assert updated.retry_count == 2
    assert updated.scheduled_at == future_time

    # Updating with wrong owner returns None
    assert job_repo.update_job(job.id, error_message="fail", owner_id="wrong-tenant") is None


def test_claim_next_job_basic_and_ordering(job_repo):
    now = datetime.now(UTC)
    # Past job (eligible)
    past_job1 = job_repo.create_job(
        ScheduledJobCreate(job_type="task", scheduled_at=now - timedelta(minutes=10)),
        owner_id="tenant-1",
    )
    # Earlier past job (eligible and should be claimed first)
    past_job2 = job_repo.create_job(
        ScheduledJobCreate(job_type="task", scheduled_at=now - timedelta(minutes=20)),
        owner_id="tenant-1",
    )
    # Future job (ineligible)
    job_repo.create_job(
        ScheduledJobCreate(job_type="task", scheduled_at=now + timedelta(minutes=15)),
        owner_id="tenant-1",
    )

    # First claim should claim the earliest job (past_job2)
    claimed1 = job_repo.claim_next_job(worker_id="worker-A", owner_id="tenant-1", now=now)
    assert claimed1 is not None
    assert claimed1.id == past_job2.id
    assert claimed1.status == ScheduledJobStatus.CLAIMED
    assert claimed1.claimed_by == "worker-A"
    assert claimed1.claimed_at is not None

    # Second claim should claim past_job1
    claimed2 = job_repo.claim_next_job(worker_id="worker-B", owner_id="tenant-1", now=now)
    assert claimed2 is not None
    assert claimed2.id == past_job1.id
    assert claimed2.status == ScheduledJobStatus.CLAIMED
    assert claimed2.claimed_by == "worker-B"

    # Third claim: no eligible jobs remain (the third is in the future)
    claimed3 = job_repo.claim_next_job(worker_id="worker-A", owner_id="tenant-1", now=now)
    assert claimed3 is None


def test_claim_next_job_lease_expiration(job_repo):
    now = datetime.now(UTC)
    past_time = now - timedelta(minutes=30)
    job = job_repo.create_job(
        ScheduledJobCreate(job_type="long_task", scheduled_at=past_time),
        owner_id="tenant-1",
    )

    # Claim the job at past_time
    claimed = job_repo.claim_next_job(
        worker_id="crashed-worker",
        owner_id="tenant-1",
        now=past_time,
        lease_duration_seconds=300,  # 5 min lease
    )
    assert claimed is not None
    assert claimed.status == ScheduledJobStatus.CLAIMED

    # Now (30 mins later), lease duration of 300s has expired
    recovered = job_repo.claim_next_job(
        worker_id="recovery-worker",
        owner_id="tenant-1",
        now=now,
        lease_duration_seconds=300,
    )
    assert recovered is not None
    assert recovered.id == job.id
    assert recovered.claimed_by == "recovery-worker"
    assert recovered.claimed_at == now


def test_complete_job(job_repo):
    now = datetime.now(UTC)
    job = job_repo.create_job(
        ScheduledJobCreate(job_type="task", scheduled_at=now),
        owner_id="tenant-1",
    )
    claimed = job_repo.claim_next_job(worker_id="worker-1", owner_id="tenant-1", now=now)
    assert claimed is not None

    completed = job_repo.complete_job(job.id, owner_id="tenant-1")
    assert completed is not None
    assert completed.status == ScheduledJobStatus.COMPLETED
    assert completed.completed_at is not None


def test_fail_job_with_and_without_retry(job_repo):
    now = datetime.now(UTC)
    job1 = job_repo.create_job(
        ScheduledJobCreate(job_type="task", scheduled_at=now),
        owner_id="tenant-1",
    )
    job_repo.claim_next_job(worker_id="worker-1", owner_id="tenant-1", now=now)

    # Fail job1 with retry
    retried = job_repo.fail_job(
        job1.id,
        error_message="HTTP 503 Service Unavailable",
        retry=True,
        retry_delay_seconds=120,
        owner_id="tenant-1",
    )
    assert retried is not None
    assert retried.status == ScheduledJobStatus.PENDING
    assert retried.retry_count == 1
    assert retried.error_message == "HTTP 503 Service Unavailable"
    assert retried.claimed_by is None
    assert retried.claimed_at is None
    assert retried.scheduled_at >= now + timedelta(seconds=119)

    # Fail job2 without retry
    job2 = job_repo.create_job(
        ScheduledJobCreate(job_type="task", scheduled_at=now),
        owner_id="tenant-1",
    )
    failed = job_repo.fail_job(
        job2.id,
        error_message="Invalid credentials, fatal error",
        retry=False,
        owner_id="tenant-1",
    )
    assert failed is not None
    assert failed.status == ScheduledJobStatus.FAILED
    assert failed.completed_at is not None
    assert failed.error_message == "Invalid credentials, fatal error"


def test_delete_job(job_repo):
    now = datetime.now(UTC)
    job = job_repo.create_job(
        ScheduledJobCreate(job_type="task", scheduled_at=now),
        owner_id="tenant-1",
    )

    # Wrong owner cannot delete
    assert job_repo.delete_job(job.id, owner_id="other-tenant") is False
    assert job_repo.get_job(job.id, owner_id="tenant-1") is not None

    # Correct owner deletes
    assert job_repo.delete_job(job.id, owner_id="tenant-1") is True
    assert job_repo.get_job(job.id, owner_id="tenant-1") is None
    assert job_repo.delete_job(job.id, owner_id="tenant-1") is False


def test_tenant_scheduled_job_repository_isolation(db_manager):
    repo_a = TenantScheduledJobRepository(db_manager, owner_id="tenant-A")
    repo_b = TenantScheduledJobRepository(db_manager, owner_id="tenant-B")

    with pytest.raises(ValueError):
        TenantScheduledJobRepository(db_manager, owner_id="")

    now = datetime.now(UTC)
    job_a = repo_a.create_job(ScheduledJobCreate(job_type="task-A", scheduled_at=now))
    job_b = repo_b.create_job(ScheduledJobCreate(job_type="task-B", scheduled_at=now))

    # Isolation: Get
    assert repo_a.get_job(job_a.id) is not None
    assert repo_a.get_job(job_b.id) is None
    assert repo_b.get_job(job_b.id) is not None
    assert repo_b.get_job(job_a.id) is None

    # Isolation: List
    list_a = repo_a.list_jobs()
    assert len(list_a) == 1
    assert list_a[0].id == job_a.id

    list_b = repo_b.list_jobs()
    assert len(list_b) == 1
    assert list_b[0].id == job_b.id

    # Isolation: Claim
    claimed_b = repo_b.claim_next_job(worker_id="worker-B", now=now)
    assert claimed_b is not None
    assert claimed_b.id == job_b.id

    claimed_a = repo_a.claim_next_job(worker_id="worker-A", now=now)
    assert claimed_a is not None
    assert claimed_a.id == job_a.id

    # Isolation: Mutation and Delete
    assert repo_a.complete_job(job_b.id) is None
    assert repo_a.fail_job(job_b.id, error_message="Error") is None
    assert repo_a.delete_job(job_b.id) is False

    assert repo_b.complete_job(job_b.id) is not None
    assert repo_b.delete_job(job_b.id) is True
