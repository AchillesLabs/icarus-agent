# 05: Dual-Engine PostgreSQL Persistence and Scheduled Jobs Migration

**GitHub Issue:** [#30](https://github.com/AchillesLabs/icarus-agent/issues/30)
**Parent Spec:** [#25](https://github.com/AchillesLabs/icarus-agent/issues/25)

**What to build:** Enhance `DatabaseManager` to natively support PostgreSQL connection pooling (`postgresql+psycopg://...`) alongside SQLite. Introduce `ScheduledJobModel` with Alembic migration `0004_scheduled_jobs_and_postgres.py` supporting one-shot reminders, scheduled tasks, status tracking (`pending`, `claimed`, `completed`, `failed`), and lease management.

**Blocked by:** [#26](https://github.com/AchillesLabs/icarus-agent/issues/26) (01: FastAPI Monorepo Application Skeleton and Health Diagnostics)

**Status:** completed

- [x] Extend `DatabaseManager` to configure connection pooling (`QueuePool`) when connected to PostgreSQL engines.
- [x] Define `ScheduledJobModel` with columns (`id`, `owner_id`, `job_type`, `scheduled_at`, `status`, `payload`, `claimed_by`, `claimed_at`, `completed_at`, `error_message`, `retry_count`).
- [x] Create `ScheduledJobRepository` for creating, querying, and updating scheduled tasks and reminders.
- [x] Add Alembic migration `0004_scheduled_jobs.py` compatible across both SQLite and PostgreSQL.
- [x] Integration tests verify database engine switching, migrations, and job model persistence.

