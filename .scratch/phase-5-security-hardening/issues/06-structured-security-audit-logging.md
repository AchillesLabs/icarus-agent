# 06: Structured Security Audit Logging (audit.jsonl) and Secret Redaction Invariant

**GitHub Issue:** Pending
**Parent Spec:** [0005-phase-5-security-hardening-vault-byok-ratelimiting.md](../../docs/specs/0005-phase-5-security-hardening-vault-byok-ratelimiting.md)

**What to build:** Implement `AuditLogger` in `icarus_core.security.audit` that writes structured security audit records to a dedicated `audit.jsonl` stream. Capture authentication outcomes, token revocations, vault changes, rate limit triggers, and cross-tenant access attempts. Enforce strict, automated secret redaction so that raw API keys, bearer tokens, and prompt messages are never written to audit logs.

**Blocked by:** [04: RESTful Server-Side BYOK Credential Vault Endpoints](04-restful-byok-credential-vault.md)

**Status:** ready-for-agent

- [ ] Implement `AuditLogger` emitting JSON Lines records with schema (`timestamp`, `event_type`, `severity`, `actor_id`, `client_ip`, `user_agent`, `request_id`, `resource_type`, `resource_id`, `action`, `outcome`, `details`).
- [ ] Wire audit logging into authentication middleware, vault routes, token routes, and rate limiter.
- [ ] Implement automated zero-leak sanitization ensuring no raw keys or bearer tokens can appear in audit records.
- [ ] Add audit log inspection tests verifying record structure, severity levels, and secret redaction invariants.
