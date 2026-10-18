# Spec 0004: Phase 4 - Remote FastAPI Server, Authenticated SSE Streaming, Dual-Engine PostgreSQL Persistence, and Background Worker Scheduler

- **GitHub Issue**: [#25](https://github.com/AchillesLabs/icarus-agent/issues/25)
- **Status**: ready-for-agent
- **Target**: Phase 4 of Icarus Agent Architecture Roadmap
- **Estimated Scope**: Remote execution API, HTTP/SSE streaming, bearer token auth, tenant isolation, PostgreSQL database support, background worker daemon, durable reminder jobs, and Docker Compose deployment.

---

## Problem Statement

In Phases 1, 2, and 3, Icarus established a robust local single-user CLI experience with autonomous tool execution, path-jail safety, real-time context token budgeting, turn-boundary history compaction, and SQLite persistence. However, the agent remains constrained exclusively to a single local machine and active terminal session:

1. **Terminal Lifespan Constraint**: If a user closes their terminal or powers down their computer, all running operations terminate immediately. The agent cannot run scheduled tasks, monitor background events, or deliver delayed reminders independently of an active terminal.
2. **Device Isolation & Lack of Portability**: Conversation histories, model configurations, and tool executions are locked inside the local `~/.icarus/icarus.db` file of one physical machine. Users cannot access their conversations or trigger tasks from multiple computers, mobile endpoints, or continuous cloud environments.
3. **Database Concurrency Ceilings**: SQLite operates with coarse table-level write locks. While ideal for single-user CLI usage, SQLite degrades under concurrent multi-process access when multiple client connections and background worker processes access the database simultaneously.
4. **Tenant Isolation Absence**: Local storage assumes a single trusted operator. There is no concept of identity verification, bearer authentication, or tenant-scoped authorization. Sharing an instance across team members or self-hosting on a public VPS would result in cross-user data leakage.
5. **No Production Deployment Artifacts**: Users who wish to self-host Icarus on a VPS or cloud instance currently have no automated Docker Compose definitions, reverse proxy configurations, TLS guidance, or database migration recipes.

Users and teams need a self-hostable remote execution service that decouples the agent runtime from the local terminal, provides secure authenticated HTTP and Server-Sent Event (SSE) streaming APIs, supports high-concurrency PostgreSQL persistence alongside SQLite, runs an autonomous background worker daemon for durable reminder jobs, and allows the Icarus CLI to switch between local and remote execution seamlessly.

---

## Solution

Build **Phase 4: Remote FastAPI Server, Authenticated SSE Streaming, Dual-Engine PostgreSQL Persistence, and Background Worker Scheduler** for the Icarus Agent platform:

1. **FastAPI Remote Execution Service (`apps/api`)**:
   - High-performance asynchronous HTTP service exposing RESTful resources for sessions, messages, runs, and reminders.
   - HTTP Bearer / API Key authentication middleware deriving tenant identity (`owner_id`) for every request; reject unauthenticated or cross-tenant access.
   - Real-time Server-Sent Events (SSE) streaming endpoint (`POST /v1/sessions/{id}/runs/stream` or `GET /v1/runs/{id}/events`) that streams model token deltas, tool call dispatch notices, tool execution outputs, compaction alerts, and terminal completion statuses directly to remote clients.
   - Run lifecycle management: start runs, inspect status, poll telemetry counters, and cleanly request cancellation (`POST /v1/runs/{id}/cancel`).

2. **Dual-Engine Persistence with PostgreSQL & Alembic (`icarus_core.persistence`)**:
   - Extend `DatabaseManager` to natively support PostgreSQL connection strings (`postgresql+psycopg://...`) with connection pooling alongside SQLite.
   - Maintain unified SQLAlchemy 2 ORM models (`SessionModel`, `MessageModel`, `AgentRunModel`, and new `ScheduledJobModel`) ensuring identical behavior across both database engines.
   - Strict tenant isolation: every query, insert, and update enforces `owner_id == authenticated_owner_id`.
   - Forward/backward Alembic migrations compatible with both SQLite and PostgreSQL.

3. **Background Worker & Task Scheduler (`apps/worker`)**:
   - Independent worker daemon process sharing `icarus_core` and `icarus_contracts`.
   - Durable scheduled job queue supporting one-shot reminders, delayed task runs, and recurring cron checks.
   - Atomic job claiming with lease timeouts and retry limits (using `SELECT ... FOR UPDATE SKIP LOCKED` on PostgreSQL, and serialized transactions on SQLite).
   - Autonomous execution: worker instantiates `AgentLoop` or notification handlers to execute jobs independently of user presence.

4. **Remote CLI Profile & Transport Client (`apps/cli`)**:
   - Server profile commands: `icarus server add <name> --url <url> --key <key>`, `icarus server list`, `icarus server switch <name>`, `icarus server remove <name>`.
   - Seamless CLI invocation: `icarus run --remote` and `icarus chat --remote` connect to the remote server over HTTPS, streaming real-time tokens with the same Rich UI, markdown rendering, and telemetry summaries as local execution.

5. **Self-Hosting Docker Compose & Operations Guide**:
   - Production multi-stage `Dockerfile` for `apps/api` and `apps/worker`.
   - `docker-compose.yml` orchestrating API server, worker daemon, PostgreSQL 16 database, volume mounts, health check probes, and Caddy reverse proxy for automated HTTPS/TLS.

---

## User Stories

1. As a developer, I want to deploy `apps/api` via Docker Compose on my VPS, so that I have a 24/7 dedicated private agent service.
2. As a CLI user, I want to run `icarus server add vps --url https://agent.myvps.com --key my-secret-token`, so that I can configure a remote server profile.
3. As a CLI user, I want to run `icarus server list`, so that I can see all configured server profiles and which one is active.
4. As a CLI user, I want to run `icarus server switch vps`, so that all subsequent commands interact with my remote server by default.
5. As a CLI user, I want to run `icarus run "Check server logs" --remote`, so that the task executes remotely on my server while tokens and tool calls stream to my local console in real time.
6. As a CLI user, I want to run `icarus chat --remote`, so that I can participate in an interactive chat session hosted on my remote server.
7. As an API client, I want to authenticate using an `Authorization: Bearer <token>` header, so that my requests are verified and bound to my tenant account.
8. As an API client, I want unauthenticated requests to return HTTP 401 Unauthorized, so that unauthorized callers cannot access the system.
9. As an API client, I want cross-tenant access to another user's sessions or runs to return HTTP 404/403, so that data leakage between tenants is strictly prevented.
10. As a frontend or CLI developer, I want to receive Server-Sent Events (SSE) during a run, so that token streaming, tool status, and compaction events update the UI live.
11. As an API client, I want to invoke `POST /v1/runs/{id}/cancel`, so that an active remote run can be cancelled cleanly mid-execution.
12. As a systems engineer, I want `GET /health` to perform deep liveness and readiness checks (including database connectivity), so that load balancers and orchestrators know when the service is healthy.
13. As a developer, I want the persistence layer to support PostgreSQL with connection pooling, so that high concurrency and multiple worker processes do not lock the database.
14. As an operator, I want Alembic migrations to apply cleanly to both SQLite and PostgreSQL, so that development and production share a unified schema.
15. As a user, I want to schedule a reminder or agent task for a future timestamp (`POST /v1/reminders`), so that the agent reminds me or executes tasks when I am offline.
16. As an operator, I want the worker process (`apps/worker`) to atomically claim pending jobs with `SKIP LOCKED`, so that multiple concurrent workers never process the same job twice.
17. As an operator, I want job leases to expire if a worker crashes, so that abandoned jobs are automatically retried rather than lost.
18. As a CLI user, I want to inspect active and completed remote reminders with `icarus reminders list`, so that I know what background tasks are pending.
19. As a developer, I want all sensitive credentials in remote runs to be masked and redacted from logs, so that secrets never leak into server stdout or CloudWatch.
20. As a self-hosting operator, I want the Docker Compose deployment to include automated TLS with Caddy, so that remote communication is encrypted over HTTPS by default without manual certificate management.

---

## Implementation Decisions

### Package Architecture & Monorepo Boundaries
- Implement `apps/api` as a dedicated FastAPI application consuming `icarus_core` and `icarus_contracts`.
- Implement `apps/worker` as an independent async service consuming `icarus_core` for scheduled task execution and atomic queue processing.
- Keep `icarus_core` free from HTTP web framework dependencies (no direct FastAPI dependencies in core).
- Extend `icarus_contracts` with typed API request and response DTOs:
  - `SessionResponse`, `SessionListResponse`
  - `RunResponse`, `RunCreateRequest`, `RunCancelResponse`
  - `SSEEventPayload` (token deltas, tool events, compaction notices, completion status)
  - `ScheduledJobCreate`, `ScheduledJobDTO`, `ScheduledJobStatus`

### Authentication & Tenant Isolation
- Simple, rock-solid token-based authentication for VPS self-hosted mode:
  - Configure `ICARUS_API_AUTH_TOKEN` (or hashed token table in DB).
  - Authenticated requests resolve to a concrete `TenantIdentity(owner_id=...)`.
  - Every repository method strictly requires and enforces `owner_id`. Repositories never execute queries without tenant scoping.

### Dual-Engine Persistence
- `DatabaseManager` dynamically configures connection parameters based on URL scheme:
  - `sqlite://...`: sets `check_same_thread=False` and pragmas (`journal_mode=WAL`, `foreign_keys=ON`).
  - `postgresql+psycopg://...` or `postgresql://...`: configures `QueuePool` with sensible pool size (default 10) and max overflow (default 20).
- Model enhancements:
  - Create `ScheduledJobModel` tracking `id`, `owner_id`, `job_type`, `scheduled_at`, `status` (`pending`, `claimed`, `completed`, `failed`), `payload`, `claimed_by`, `claimed_at`, `completed_at`, `error_message`, and `retry_count`.
  - Alembic migration `0004_scheduled_jobs_and_postgres.py` creates table and indexes (`owner_id`, `status`, `scheduled_at`).

### Background Worker & Scheduler Daemon
- `apps/worker` runs an async polling loop (`asyncio.sleep` with backoff).
- Atomic claim query:
  - On PostgreSQL: `SELECT * FROM scheduled_jobs WHERE status = 'pending' AND scheduled_at <= NOW() FOR UPDATE SKIP LOCKED LIMIT 1`.
  - On SQLite: serialized immediate transaction with state update.
- Worker executes job:
  - For agent runs: calls `AgentLoop.run` in headless mode and records results in `AgentRunModel`.
  - For notifications: dispatches configured notification channel and marks job `completed`.
- Failed jobs update status to `failed` and record error traceback.

### Remote CLI Client
- Implement `RemoteAgentClient` in `apps/cli`:
  - Uses `httpx.AsyncClient` or `httpx.Client` with configured base URL and API key.
  - Implements SSE streaming parser decoding server events and forwarding them to `RichAgentObserver`.
  - Implements remote session management: list, fetch history, create sessions.
- Profile storage in `~/.icarus/config.toml`:
  - `[servers.<name>]`: `url`, `active`.
  - API keys stored in OS keyring (or masked in config if keyring unavailable).

---

## Testing Decisions

### What Makes a Good Test
- Tests must verify observable HTTP contracts, status codes, and JSON schemas rather than FastAPI internals.
- Tests must prove cross-tenant isolation: User A cannot see, read, modify, or cancel User B's sessions, runs, or scheduled jobs.
- Tests must verify Server-Sent Events (SSE) streaming order: `turn_start` &rarr; `token` &rarr; `tool_start` &rarr; `tool_end` &rarr; `completion`.
- Tests must verify worker claiming atomicity: two concurrent worker tasks must never execute the same job twice.
- Tests must run cleanly against SQLite in CI without requiring an active external PostgreSQL cluster, while providing a dedicated PostgreSQL integration test fixture when `TEST_POSTGRES_URL` is set.

### Primary Testing Seams
1. **API HTTP Seam (`TestClient(app)` / `httpx.AsyncClient`)**:
   - Exercise the entire FastAPI endpoint surface: authentication, sessions CRUD, run creation, SSE stream consumption, and run cancellation against a test database.
2. **Worker Claiming & Execution Seam (`JobExecutor.claim_next_job`)**:
   - Seed pending scheduled jobs, trigger worker tick, and verify state transitions (`pending` &rarr; `claimed` &rarr; `completed`/`failed`), lease expiration, and error recording.
3. **Remote CLI Profile & Transport Seam (`CliRunner` with mock HTTP transport)**:
   - Verify `icarus server add/list/switch` and verify `icarus run --remote` and `icarus sessions --remote` correctly invoke remote HTTP endpoints and render Rich tables/panels.

### Prior Art in Codebase
- `tests/test_cli.py`: Demonstrates Typer CLI testing with `CliRunner`.
- `tests/test_run_telemetry.py`: Demonstrates verifying agent run persistence and budget counters.
- `tests/test_sessions_cli.py`: Demonstrates Rich table rendering and transcript inspection.
- `tests/test_database.py` & `tests/test_migrations.py`: Demonstrates database connection lifecycle and Alembic migration verification.

---

## Out of Scope

- AWS EC2/Lightsail production infrastructure deployment, CloudWatch metric alarms, and IAM roles (Phase 6).
- Cross-platform desktop application using Tauri 2 and bundled Python sidecar (Phase 7).
- Public multi-tenant billing, stripe payment webhooks, and SaaS user subscription tiers.
- Browser-based Next.js web application chat interface.
- Kubernetes Helm charts and distributed Celery/Redis clusters (modular monolith first).

---

## Further Notes

### Tracer-Bullet Implementation Plan (7 Tickets)
1. **[Ticket 1: FastAPI Monorepo Application Skeleton & Health Diagnostics](https://github.com/AchillesLabs/icarus-agent/issues/26)** (`#26` - `apps/api` initialization, configuration, dependency injection, and `/health` probes).
2. **[Ticket 2: Bearer Authentication & Tenant-Isolated Resource Dependencies](https://github.com/AchillesLabs/icarus-agent/issues/27)** (`#27` - API key authentication middleware and tenant-filtered request scoping).
3. **[Ticket 3: RESTful Session & Message HTTP Endpoints](https://github.com/AchillesLabs/icarus-agent/issues/28)** (`#28` - `GET/POST /v1/sessions` and `/v1/sessions/{id}/messages` with validation and pagination).
4. **[Ticket 4: Server-Sent Events (SSE) Agent Run Streaming & Cancellation](https://github.com/AchillesLabs/icarus-agent/issues/29)** (`#29` - `POST /v1/sessions/{id}/runs/stream` emitting live tokens, tool progress, and cancel endpoint).
5. **[Ticket 5: Dual-Engine PostgreSQL Support & Alembic Scheduled Jobs Migration](https://github.com/AchillesLabs/icarus-agent/issues/30)** (`#30` - `DatabaseManager` Postgres pooling, `ScheduledJobModel`, and Alembic migration).
6. **[Ticket 6: Autonomous Background Worker & Durable Job Scheduler](https://github.com/AchillesLabs/icarus-agent/issues/31)** (`#31` - `apps/worker` daemon, atomic job claiming, lease timeout handling, and run dispatch).
7. **[Ticket 7: Remote CLI Profile Management & Remote Execution Streaming](https://github.com/AchillesLabs/icarus-agent/issues/32)** (`#32` - `icarus server` commands and `--remote` execution parity with Rich console UI).
