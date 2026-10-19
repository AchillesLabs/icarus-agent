# 04: RESTful Server-Side BYOK Credential Vault Endpoints

**GitHub Issue:** Pending
**Parent Spec:** [0005-phase-5-security-hardening-vault-byok-ratelimiting.md](../../docs/specs/0005-phase-5-security-hardening-vault-byok-ratelimiting.md)

**What to build:** Expose complete RESTful API resources for tenant model provider credentials: `GET /v1/vault/credentials` (list configured credentials with masked secrets), `POST /v1/vault/credentials` (encrypt and store or update provider credential), and `DELETE /v1/vault/credentials/{provider}` (delete stored credential). Strictly enforce tenant isolation so secrets are completely segregated across accounts.

**Blocked by:** [02: Database Models and Alembic Migration for Vault Credentials and API Tokens](02-database-models-and-vault-migration.md)

**Status:** ready-for-agent

- [ ] Add `VaultCredentialCreate`, `VaultCredentialResponse`, and `VaultCredentialSummary` DTOs in `icarus_contracts`.
- [ ] Implement `GET /v1/vault/credentials` returning masked previews of configured provider credentials.
- [ ] Implement `POST /v1/vault/credentials` encrypting provider keys with `CredentialVault` before persistence.
- [ ] Implement `DELETE /v1/vault/credentials/{provider}` removing stored credentials.
- [ ] API integration tests verify encrypted storage, secret masking in responses, and cross-tenant access rejection.
