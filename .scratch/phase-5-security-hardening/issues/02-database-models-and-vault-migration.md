# 02: Database Models and Alembic Migration for Vault Credentials and API Tokens

**GitHub Issue:** Pending
**Parent Spec:** [0005-phase-5-security-hardening-vault-byok-ratelimiting.md](../../docs/specs/0005-phase-5-security-hardening-vault-byok-ratelimiting.md)

**What to build:** Create SQLAlchemy 2 ORM models `TenantCredentialModel` and `TenantApiTokenModel` in `icarus_core.persistence.models`. Implement tenant-scoped repositories `TenantCredentialRepository` and `TenantApiTokenRepository`. Add Alembic migration `0005_vault_and_api_tokens.py` compatible with both SQLite and PostgreSQL.

**Blocked by:** [01: Cryptographic Credential Vault and Secret Masking Architecture](01-cryptographic-vault-and-secret-masking.md)

**Status:** ready-for-agent

- [ ] Define `TenantCredentialModel` with columns (`id`, `owner_id`, `provider`, `encrypted_secret`, `key_hint`, `created_at`, `updated_at`) and unique constraint on `(owner_id, provider)`.
- [ ] Define `TenantApiTokenModel` with columns (`id`, `owner_id`, `name`, `token_hash`, `prefix`, `expires_at`, `revoked_at`, `last_used_at`, `created_at`).
- [ ] Implement `TenantCredentialRepository` and `TenantApiTokenRepository` with strict tenant isolation.
- [ ] Create Alembic migration `0005_vault_and_api_tokens.py` updating both SQLite and PostgreSQL schemas.
- [ ] Integration tests verify database engine compatibility, constraints, and repository CRUD operations.
