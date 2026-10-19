# 01: Cryptographic Credential Vault and Secret Masking Architecture

**GitHub Issue:** Pending
**Parent Spec:** [0005-phase-5-security-hardening-vault-byok-ratelimiting.md](../../docs/specs/0005-phase-5-security-hardening-vault-byok-ratelimiting.md)

**What to build:** Implement `CredentialVault` in `icarus_core.security.vault` providing authenticated symmetric encryption (AES-256-GCM / Fernet) derived from `ICARUS_VAULT_MASTER_KEY` (with a secure development fallback). Implement secret masking utility (`mask_secret`) producing safe string representations (e.g. `sk-...4a2b`) for logging, CLI output, and HTTP responses.

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [ ] Add `cryptography` dependency to `packages/agent-core` if needed and export security utilities.
- [ ] Implement `CredentialVault` with `encrypt(secret: str) -> str` and `decrypt(ciphertext: str) -> str`.
- [ ] Implement master key derivation with validation (rejecting weak or corrupt keys).
- [ ] Implement `mask_secret(secret: str, prefix_len: int = 3, suffix_len: int = 4) -> str` for safe display.
- [ ] Add comprehensive unit tests in `tests/test_vault.py` verifying encryption, decryption, tampering detection, and masking.
