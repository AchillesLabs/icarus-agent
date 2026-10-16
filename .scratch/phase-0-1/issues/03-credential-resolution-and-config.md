# 03: Credential Resolution Pipeline and Interactive Configuration

**What to build:** Build the credential management and user configuration system. Implement `icarus init` for guided initial onboarding and `icarus config list/set` for tuning model settings. Implement the hierarchical credential resolver: (1) CLI argument `--api-key`, (2) Environment variable `XAI_API_KEY` / `OPENROUTER_API_KEY` / `ICARUS_API_KEY`, (3) OS Keyring via `keyring`, (4) Actionable error prompt in headless environments. Secrets are stored in the OS keyring and never written in plaintext to `~/.icarus/config.toml`.

**Blocked by:** 01: Monorepo Foundation and Health Doctor Tracer Bullet

**Status:** closed

- [x] Configuration manager loads and persists non-sensitive settings (default provider, model, temperature, budget) in `~/.icarus/config.toml`.
- [x] Credential resolver implements the 4-tier lookup hierarchy without leaking raw keys into logs or config files.
- [x] `icarus init` guides the user through setting up their primary provider (default Grok) and securely saves the API key to the OS keyring.
- [x] `icarus config list` and `icarus config set <key> <val>` allow inspecting and updating configuration with masked secrets.
- [x] `icarus doctor` checks credential availability and masked key display without revealing secret values.
- [x] Tests verify credential resolution order and mock keyring behavior.
