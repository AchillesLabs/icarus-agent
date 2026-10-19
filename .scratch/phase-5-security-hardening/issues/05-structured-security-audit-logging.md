# 05: Structured Security Audit Logging (audit.jsonl) with Secret Redaction

**GitHub Issue:** [#38](https://github.com/AchillesLabs/icarus-agent/issues/38)
**Parent Spec:** [#33](https://github.com/AchillesLabs/icarus-agent/issues/33)

**What to build:** Establish a dedicated, structured security audit stream recording security-critical events across authentication, credential vault modifications, token revocations, rate limit violations, and cross-tenant access attempts. Records are formatted as append-only JSON Lines with actor attribution, client IP, timestamps, and severity classifications. Enforces an automated zero-leak redaction filter ensuring raw credentials, bearer tokens, and private message payloads never appear in audit logs.

**Blocked by:**
- [#34](https://github.com/AchillesLabs/icarus-agent/issues/34) (01: Dynamic API Token Issuance, Constant-Time Verification, and Instant Revocation)
- [#35](https://github.com/AchillesLabs/icarus-agent/issues/35) (02: Encrypted Credential Vault and Server-Side BYOK Management)
- [#37](https://github.com/AchillesLabs/icarus-agent/issues/37) (04: Per-Tenant Sliding-Window Rate Limiting and Concurrency Throttling)

**Status:** ready-for-agent

- [ ] Implement structured audit logging facility emitting JSON Lines records to `audit.jsonl` and configured loggers.
- [ ] Define standardized audit schema covering timestamps, event type, severity, actor ID, client IP, user agent, request ID, resource, action, and outcome.
- [ ] Hook audit logger into authentication (successes, failures, revoked tokens), vault operations, token revocations, and rate limit triggers.
- [ ] Implement automated zero-leak sanitization guaranteeing that raw API keys, authorization tokens, and prompt messages are redacted.
- [ ] Automated audit tests verify event emission, record schema completeness, severity classifications, and secret redaction invariants.
