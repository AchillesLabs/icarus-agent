# 07: Remote CLI Server Profile Management and Remote Execution Parity

**What to build:** Add `icarus server` CLI management commands (`add`, `list`, `switch`, `remove`) in `apps/cli`. Implement `RemoteAgentClient` connecting to `apps/api` via HTTPS and parsing SSE event streams. When `--remote` or an active remote server profile is used, `icarus run` and `icarus chat` stream tokens, execute tools, and render Rich markdown identically to local execution. Include Docker Compose and self-hosting documentation.

**Blocked by:**
- 04: Server-Sent Events (SSE) Agent Run Streaming and Cancellation
- 06: Autonomous Background Worker Daemon and Task Scheduler

**Status:** ready-for-agent

- [ ] Implement `icarus server add`, `list`, `switch`, and `remove` commands managing remote profiles in `~/.icarus/config.toml`.
- [ ] Implement `RemoteAgentClient` with SSE streaming parser decoding events and feeding `RichAgentObserver`.
- [ ] Update `icarus run` and `icarus chat` to execute via `RemoteAgentClient` when `--remote` flag or remote profile is active.
- [ ] Add production multi-stage `Dockerfile` and `docker-compose.yml` for API, Worker, PostgreSQL, and Caddy reverse proxy.
- [ ] End-to-end integration tests verify remote CLI streaming, server profile switching, and parity with local UI output.
