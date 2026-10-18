# 01: FastAPI Monorepo Application Skeleton and Health Diagnostics

**What to build:** Scaffold the `apps/api` FastAPI service package within the uv monorepo workspace. Configure application lifespan, CORS policies, global exception handlers for normalized JSON errors, dependency injection architecture, and deep liveness/readiness `/health` diagnostic endpoints verifying database engine connectivity and system state.

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [ ] Scaffold `apps/api` package with `pyproject.toml` and wire into monorepo root workspace dependencies.
- [ ] Create FastAPI application factory with lifespan management, CORS configuration, and structured JSON error handlers.
- [ ] Implement `GET /health` and `GET /health/ready` endpoints returning status, version, uptime, and database connectivity state.
- [ ] Implement dependency injection providers for configuration, database session scopes, and repository access.
- [ ] Integration tests verify application startup, health probes, and database ping behavior via `httpx.AsyncClient` / `TestClient`.
