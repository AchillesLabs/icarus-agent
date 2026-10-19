# 01: Dynamic API Token Issuance, Constant-Time Verification, and Instant Revocation

**GitHub Issue:** [#34](https://github.com/AchillesLabs/icarus-agent/issues/34)
**Parent Spec:** [#33](https://github.com/AchillesLabs/icarus-agent/issues/33)

**What to build:** Enable tenants to dynamically generate, name, inspect, and immediately revoke API access tokens instead of relying on static environment configuration. Tokens are hashed with SHA-256 before database persistence and verified using constant-time comparison to prevent timing attacks. An in-memory cache accelerates active token lookups, while revocation immediately invalidates cached tokens so compromised credentials are synchronously rejected with HTTP 401.

**Blocked by:** None (can start immediately)

**Status:** closed

- [x] New database model and migration for API tokens storing tenant owner, friendly token name, SHA-256 token hash, prefix, creation date, and optional expiration/revocation timestamps.
- [x] Endpoint `POST /v1/auth/tokens` issues a new cryptographically random API token, hashes and persists it, and returns the plaintext secret exactly once.
- [x] Endpoint `GET /v1/auth/tokens` returns the list of active and revoked tokens for the authenticated tenant with names, prefixes, creation dates, and last used timestamps.
- [x] Endpoint `POST /v1/auth/tokens/{id}/revoke` immediately marks a token as revoked and purges it from in-memory validation caches.
- [x] FastAPI authentication dependency validates incoming Bearer tokens against the database-backed token store using constant-time verification.
- [x] Integration tests verify dynamic token generation, successful authentication, constant-time validation, and immediate rejection of revoked or expired tokens.
