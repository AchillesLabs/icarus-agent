# 02: Bearer Authentication Middleware and Tenant-Isolated Request Scoping

**GitHub Issue:** [#27](https://github.com/AchillesLabs/icarus-agent/issues/27)
**Parent Spec:** [#25](https://github.com/AchillesLabs/icarus-agent/issues/25)

**What to build:** Implement HTTP Bearer and API key authentication middleware for `apps/api`. Authenticated requests are bound to a verified `TenantIdentity` with an immutable `owner_id`. Enforce strict tenant isolation across all route dependencies so that missing/invalid credentials yield HTTP 401, and cross-tenant resource requests yield HTTP 404/403.

**Blocked by:** [#26](https://github.com/AchillesLabs/icarus-agent/issues/26) (01: FastAPI Monorepo Application Skeleton and Health Diagnostics)

**Status:** ready-for-agent

- [ ] Implement `HTTPBearer` security dependency validating API tokens against configured service secrets (`ICARUS_API_AUTH_TOKEN`).
- [ ] Bind authenticated identity into request state with immutable `owner_id` context.
- [ ] Implement tenant-scoped database session and repository dependencies in `apps/api`.
- [ ] Verify unauthenticated requests return HTTP 401 with standard error schema.
- [ ] Security tests prove cross-tenant access rejection (requests for resources owned by another tenant fail with 404/403).
