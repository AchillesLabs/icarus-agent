# 04: Per-Tenant Sliding-Window Rate Limiting and Concurrency Throttling

**GitHub Issue:** [#37](https://github.com/AchillesLabs/icarus-agent/issues/37)
**Parent Spec:** [#33](https://github.com/AchillesLabs/icarus-agent/issues/33)

**What to build:** Safeguard the API and background worker against denial-of-service, request flooding, and runaway agent loops by enforcing per-tenant rate limits and concurrency ceilings. Requests are throttled using an in-memory sliding window algorithm, and concurrent active runs are bounded. When thresholds are exceeded, the server returns an RFC 6585 compliant HTTP 429 response with a Retry-After header and standard rate limiting status headers.

**Blocked by:** [#34](https://github.com/AchillesLabs/icarus-agent/issues/34) (01: Dynamic API Token Issuance, Constant-Time Verification, and Instant Revocation)

**Status:** ready-for-agent

- [ ] Implement an in-memory sliding-window rate limiter tracking requests per minute (RPM) per tenant identity.
- [ ] Implement an active execution concurrency tracker bounding the number of simultaneous active agent runs per tenant.
- [ ] Middleware injects standard rate limiting response headers (`X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`).
- [ ] Return standard `HTTP 429 Too Many Requests` responses with `Retry-After` header when rate limits or concurrency ceilings are reached.
- [ ] Concurrency and rate limiting tests verify sliding window accuracy, burst handling, concurrent run limits, and recovery after reset.
