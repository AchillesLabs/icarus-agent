# 01: Dynamic API Token Issuance, Constant-Time Verification, and Instant Revocation

**What to build:** Enable tenants to dynamically generate, name, inspect, and immediately revoke API access tokens instead of relying on static environment configuration. Tokens are hashed with SHA-256 before database persistence and verified using constant-time comparison to prevent timing attacks. An in-memory cache accelerates active token lookups, while revocation immediately invalidates cached tokens so compromised credentials are synchronously rejected with HTTP 401.

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [ ] New database model and migration for API tokens storing tenant owner, friendly token name, SHA-256 token hash, prefix, creation date, and optional expiration/revocation timestamps.
- [ ] Endpoint `POST /v1/auth/tokens` issues a new cryptographically random API token, hashes and persists it, and returns the plaintext secret exactly once.
- [ ] Endpoint `GET /v1/auth/tokens` returns the list of active and revoked tokens for the authenticated tenant with names, prefixes, creation dates, and last used timestamps.
- [ ] Endpoint `POST /v1/auth/tokens/{id}/revoke` immediately marks a token as revoked and purges it from in-memory validation caches.
- [ ] FastAPI authentication dependency validates incoming Bearer tokens against the database-backed token store using constant-time verification.
- [ ] Integration tests verify dynamic token generation, successful authentication, constant-time validation, and immediate rejection of revoked or expired tokens.
