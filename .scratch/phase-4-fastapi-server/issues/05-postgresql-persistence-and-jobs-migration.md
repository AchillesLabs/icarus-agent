# 05: Dual-Engine PostgreSQL Persistence and Scheduled Jobs Migration

**What to build:** Enhance `DatabaseManager` to natively support PostgreSQL connection pooling (`postgresql+psycopg://...`) alongside SQLite. Introduce `ScheduledJobModel` with Alembic migration `0004_scheduled_jobs_and_postgres.py` supporting one-shot reminders, scheduled tasks, status tracking (`pending`, `claimed`, `completed`, `failed`), and lease management.

**Blocked by:** 01: FastAPI Monorepo Application Skeleton and Health Diagnostics

**Status:** ready-for-agent

- [ ] Extend `DatabaseManager` to configure connection pooling (`QueuePool`) when connected to PostgreSQL engines.
- [ ] Define `ScheduledJobModel` with columns (`id`, `owner_id`, `job_type`, `scheduled_at`, `status`, `payload`, `claimed_by`, `claimed_at`, `completed_at`, `error_message`, `retry_count`).
- [ ] Create `ScheduledJobRepository` for creating, querying, and updating scheduled tasks and reminders.
- [ ] Add Alembic migration `0004_scheduled_jobs.py` compatible across both SQLite and PostgreSQL.
- [ ] Integration tests verify database engine switching, migrations, and job model persistence.
