# 02: Storage Engine and Automatic Migrations Tracer Bullet

**What to build:** Build the persistent storage foundation for single-user local mode in `~/.icarus/`. Define core SQLAlchemy 2 models (`SessionModel`, `MessageModel`, `AgentRunModel`), session and message repository interfaces, and integrate automated Alembic migration execution on CLI startup so the local database is always schema-synchronized without manual user intervention. Verify database connectivity and schema migration state directly inside `icarus doctor`.

**Blocked by:** 01: Monorepo Foundation and Health Doctor Tracer Bullet

**Status:** closed

- [x] SQLAlchemy 2 mapped entities created for sessions, messages, and agent runs under `icarus_core.persistence`.
- [x] Repository interfaces defined for creating, reading, listing, and updating sessions and messages.
- [x] SQLite database connection manager defaults to `~/.icarus/icarus.db` with support for test overrides (`sqlite:///:memory:`).
- [x] Alembic migrations configured within `icarus_core` and automatically executed on startup when pending revisions exist.
- [x] `icarus doctor` inspects database connectivity, table existence, and migration revision status.
- [x] Repository and migration tests pass against in-memory and file-based SQLite engines.
