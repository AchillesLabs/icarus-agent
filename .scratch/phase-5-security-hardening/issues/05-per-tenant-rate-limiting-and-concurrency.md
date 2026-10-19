# 05: Per-Tenant Sliding-Window Rate Limiting and Concurrency Throttling Middleware

**GitHub Issue:** Pending
**Parent Spec:** [0005-phase-5-security-hardening-vault-byok-ratelimiting.md](../../docs/specs/0005-phase-5-security-hardening-vault-byok-ratelimiting.md)

**What to build:** Implement a high-performance in-memory sliding window rate limiter and active execution concurrency tracker in `apps/api`. Throttle requests per minute (RPM) and bound simultaneous active agent runs per tenant. Include standard `X-RateLimit-*` headers and return `HTTP 429 Too Many Requests` with `Retry-After` header when limits are reached.

**Blocked by:** [03: Dynamic API Token Issuance, Constant-Time Verification, and Instant Revocation](03-dynamic-api-tokens-and-revocation.md)

**Status:** ready-for-agent

- [ ] Implement `SlidingWindowRateLimiter` tracking request timestamps and active concurrent runs per tenant key.
- [ ] Implement FastAPI middleware attaching rate limit headers (`X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`).
- [ ] Enforce concurrent run ceilings (rejecting or queueing runs when active concurrency limit is reached).
- [ ] Return RFC 6585 compliant `HTTP 429` responses with `Retry-After` header.
- [ ] Concurrency and rate limit unit tests verify sliding window accuracy, burst handling, and header correctness.
