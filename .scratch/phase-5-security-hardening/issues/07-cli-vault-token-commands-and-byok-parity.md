# 07: CLI Vault and Token Management Commands with Dynamic BYOK Run Integration

**GitHub Issue:** Pending
**Parent Spec:** [0005-phase-5-security-hardening-vault-byok-ratelimiting.md](../../docs/specs/0005-phase-5-security-hardening-vault-byok-ratelimiting.md)

**What to build:** Add Typer CLI command suites `icarus vault` (`set`, `list`, `remove`) and `icarus token` (`create`, `list`, `revoke`) in `apps/cli`. Wire dynamic BYOK credential resolution into `apps/api` agent execution (`POST /v1/sessions/{id}/runs/stream`) so tenant-specific vault keys are loaded ephemerally for runs without leaking into history or logs. Add prompt injection canary penetration tests.

**Blocked by:**
- [04: RESTful Server-Side BYOK Credential Vault Endpoints](04-restful-byok-credential-vault.md)
- [05: Per-Tenant Sliding-Window Rate Limiting and Concurrency Throttling Middleware](05-per-tenant-rate-limiting-and-concurrency.md)
- [06: Structured Security Audit Logging (audit.jsonl) and Secret Redaction Invariant](06-structured-security-audit-logging.md)

**Status:** ready-for-agent

- [ ] Implement `icarus vault set`, `list`, and `remove` commands communicating with the active remote server profile.
- [ ] Implement `icarus token create`, `list`, and `revoke` commands in `apps/cli`.
- [ ] Connect dynamic BYOK provider key resolution in `POST /v1/sessions/{id}/runs/stream` to initialize provider instances using tenant's vault key.
- [ ] Implement prompt injection canary penetration tests verifying secrets are never output or leaked by model turns.
- [ ] End-to-end integration tests verify remote CLI vault management and BYOK run execution.
