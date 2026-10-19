# 01: Tiered Health Probes (/health/live, /health/ready) and Worker Heartbeat Tracking

**GitHub Issue:** [#42](https://github.com/AchillesLabs/icarus-agent/issues/42)
**Parent Spec:** [#41](https://github.com/AchillesLabs/icarus-agent/issues/41)

**What to build:** Tiered health routing allowing container orchestrators and reverse proxies to distinguish between a responsive event loop (/health/live) and a fully initialized instance (/health/ready). Background worker daemons write periodic status heartbeats to the database, allowing readiness probes to detect stalled or crashed schedulers alongside PostgreSQL connection pool saturation and pending Alembic migrations.

**Blocked by:**
- None (can start immediately)

**Status:** ready-for-agent

- [ ] Implement /health/live returning 200 OK immediately when FastAPI event loop is responsive.
- [ ] Implement /health/ready performing deep dependency verification: PostgreSQL pool connectivity, Alembic migration currency, and worker daemon heartbeat freshness.
- [ ] Implement worker heartbeat persistence updating a worker_heartbeats record or table periodically during task polling loops.
- [ ] Readiness probe returns 503 Service Unavailable with structured diagnostics if database is unreachable, migrations are pending, or worker heartbeat exceeds timeout threshold.
- [ ] Unit and integration tests verify /health/live, /health/ready, and worker heartbeat failure modes.
