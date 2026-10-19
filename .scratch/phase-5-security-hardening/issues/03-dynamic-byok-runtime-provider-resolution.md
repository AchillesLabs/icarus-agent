# 03: Dynamic BYOK Model Provider Resolution in Remote Agent Runs

**GitHub Issue:** [#36](https://github.com/AchillesLabs/icarus-agent/issues/36)
**Parent Spec:** [#33](https://github.com/AchillesLabs/icarus-agent/issues/33)

**What to build:** Dynamically resolve and inject a tenant's vault-stored provider credentials into the execution runtime during remote agent runs and streaming sessions. When a tenant initiates an agent run, the server decrypts the tenant's BYOK credential ephemerally in memory to configure the model provider adapter. The decrypted secret is strictly isolated to the run invocation and is never persisted into session history, compaction summaries, application logs, or error responses.

**Blocked by:** [#35](https://github.com/AchillesLabs/icarus-agent/issues/35) (02: Encrypted Credential Vault and Server-Side BYOK Management)

**Status:** closed

- [x] Connect tenant vault repository to the agent execution pipeline in the streaming and one-shot run endpoints.
- [x] Dynamically resolve tenant-specific provider credentials during run creation, falling back to system defaults only when permitted.
- [x] Instantiate isolated model provider instances configured with the tenant's decrypted API key.
- [x] Enforce zero-leak invariant: ensure provider credentials are never written to session messages, context summaries, or error messages.
- [x] Integration tests verify streaming runs and one-shot queries execute successfully using the tenant's vault-stored BYOK credentials.
