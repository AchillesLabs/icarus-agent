# 03: Dynamic API Token Issuance, Constant-Time Verification, and Instant Revocation

**GitHub Issue:** Pending
**Parent Spec:** [0005-phase-5-security-hardening-vault-byok-ratelimiting.md](../../docs/specs/0005-phase-5-security-hardening-vault-byok-ratelimiting.md)

**What to build:** Implement secure dynamic API token issuance, SHA-256 token hashing, constant-time validation (`hmac.compare_digest`), and instant revocation. Expose `POST /v1/auth/tokens`, `GET /v1/auth/tokens`, and `POST /v1/auth/tokens/{id}/revoke`. Update FastAPI authentication dependency to authenticate against database-backed tokens with in-memory caching and immediate invalidation.

**Blocked by:** [02: Database Models and Alembic Migration for Vault Credentials and API Tokens](02-database-models-and-vault-migration.md)

**Status:** ready-for-agent

- [ ] Implement secure random token generator producing standard prefixes (`sk_icarus_...`).
- [ ] Implement SHA-256 token hashing and constant-time comparison in authentication middleware.
- [ ] Implement `POST /v1/auth/tokens` returning plaintext secret once upon creation.
- [ ] Implement `GET /v1/auth/tokens` listing active and revoked token metadata.
- [ ] Implement `POST /v1/auth/tokens/{id}/revoke` providing instant access revocation.
- [ ] Integration and security tests verify token creation, authentication, expiration, and revoked token rejection (HTTP 401).
