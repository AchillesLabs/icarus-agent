# 06: Autonomous Background Worker Daemon and Task Scheduler

**What to build:** Implement `apps/worker` as an independent async daemon process that polls and claims pending scheduled jobs atomically using `SELECT ... FOR UPDATE SKIP LOCKED` on PostgreSQL (and serialized locks on SQLite). Executes headless `AgentLoop` tasks and reminder dispatches, recovers expired leases after crashes, and persists execution results.

**Blocked by:** 05: Dual-Engine PostgreSQL Persistence and Scheduled Jobs Migration

**Status:** ready-for-agent

- [ ] Scaffold `apps/worker` package with async worker daemon lifecycle and polling loop.
- [ ] Implement atomic job claiming logic (`claim_next_job`) using `SKIP LOCKED` to prevent duplicate concurrent execution.
- [ ] Implement job lease timeout and orphan recovery mechanism for crashed worker runs.
- [ ] Implement job dispatch execution handler running headless `AgentLoop` or notification handlers.
- [ ] Unit and concurrency tests verify atomic claiming, lease expiration recovery, and result persistence.
