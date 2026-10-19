# 06: Remote CLI Security Management (icarus vault and icarus token)

**What to build:** Provide interactive CLI commands allowing developers and operators to manage server-side BYOK provider credentials and remote API access tokens directly from their terminal. Commands under `icarus vault` (`set`, `list`, `remove`) and `icarus token` (`create`, `list`, `revoke`) communicate with the active remote server profile and format information using styled Rich tables with masked secret previews.

**Blocked by:**
- 01: Dynamic API Token Issuance, Constant-Time Verification, and Instant Revocation
- 02: Encrypted Credential Vault and Server-Side BYOK Management

**Status:** ready-for-agent

- [ ] Implement `icarus vault set <provider> --key <secret>` uploading and encrypting credentials on the active remote server.
- [ ] Implement `icarus vault list` rendering a styled Rich table of configured provider keys with masked previews.
- [ ] Implement `icarus vault remove <provider>` removing a configured credential from the server vault.
- [ ] Implement `icarus token create <name>` generating and safely displaying a new remote API token.
- [ ] Implement `icarus token list` and `icarus token revoke <id>` displaying active/revoked tokens and revoking credentials.
- [ ] CLI integration tests verify interactive command execution, Rich table outputs, and remote API client parity.
