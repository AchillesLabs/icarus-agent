# 02: Encrypted Credential Vault and Server-Side BYOK Management

**GitHub Issue:** [#35](https://github.com/AchillesLabs/icarus-agent/issues/35)
**Parent Spec:** [#33](https://github.com/AchillesLabs/icarus-agent/issues/33)

**What to build:** Allow tenants to securely store their own model provider credentials (such as Groq, OpenRouter, Anthropic, OpenAI, or Grok) on the server using authenticated symmetric encryption at rest. Keys are encrypted using AES-256-GCM / Fernet derived from a dedicated vault master secret. RESTful endpoints allow tenants to register, view masked previews of, and remove their provider keys without exposing plaintext secrets in database backups or API responses.

**Blocked by:** [#34](https://github.com/AchillesLabs/icarus-agent/issues/34) (01: Dynamic API Token Issuance, Constant-Time Verification, and Instant Revocation)

**Status:** ready-for-agent

- [ ] Implement cryptographic credential vault with authenticated encryption and decryption backed by a vault master key.
- [ ] Database model and migration for tenant credentials storing tenant owner, provider identifier, encrypted secret ciphertext, and masked key preview hint.
- [ ] Implement `POST /v1/vault/credentials` encrypting provider keys before persistence and returning masked confirmation.
- [ ] Implement `GET /v1/vault/credentials` listing all configured provider credentials for the authenticated tenant with masked previews.
- [ ] Implement `DELETE /v1/vault/credentials/{provider}` removing a stored provider credential.
- [ ] Integration tests verify encryption at rest, key masking in responses, tampering detection, and complete tenant isolation.
