# 07: Threat-Model Security Hardening and Penetration Test Matrix

**GitHub Issue:** [#40](https://github.com/AchillesLabs/icarus-agent/issues/40)
**Parent Spec:** [#33](https://github.com/AchillesLabs/icarus-agent/issues/33)

**What to build:** Enforce and validate all Phase 5 security release gates through an automated penetration and threat-model test suite. Verifies that the agent loop refuses prompt-injection attempts attempting to extract vault keys or internal configs via canary tests, that token verification resists timing attacks, that cross-tenant resource tampering and ID enumeration are rejected with 404/403, and that automated scanners detect zero plaintext secrets across database tables, application logs, and HTTP payloads.

**Blocked by:**
- [#36](https://github.com/AchillesLabs/icarus-agent/issues/36) (03: Dynamic BYOK Model Provider Resolution in Remote Agent Runs)
- [#38](https://github.com/AchillesLabs/icarus-agent/issues/38) (05: Structured Security Audit Logging (audit.jsonl) with Secret Redaction)
- [#39](https://github.com/AchillesLabs/icarus-agent/issues/39) (06: Remote CLI Security Management (icarus vault and icarus token))

**Status:** closed

- [x] Implement prompt injection canary tests verifying that malicious tool outputs or user prompts cannot coerce the model into leaking system secrets or vault keys.
- [x] Implement timing attack resistance tests verifying constant-time token comparison behavior.
- [x] Implement automated cross-tenant penetration tests verifying complete isolation across vault credentials, tokens, runs, sessions, and audit records under ID enumeration fuzzing.
- [x] Implement automated plaintext secret scanner inspecting database dumps, log files, and HTTP payloads to prove zero secrets are exposed.
- [x] All security release gates pass and automated tests execute reliably in CI with mock providers.
