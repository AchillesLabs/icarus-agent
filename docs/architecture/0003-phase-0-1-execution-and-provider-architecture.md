# ADR 0003: Phase 0/1 Architecture, Storage, and Hybrid Provider Strategy

- **Status**: Accepted
- **Date**: 2026-10-16
- **Context**: Finalizing Round 2 decisions and provider strategy for Icarus-Agent Phase 0 & 1 implementation.

## Decisions

1. **Storage Layout**:
   - Centralize all local user state in `~/.icarus/`:
     - Configuration: `~/.icarus/config.toml`
     - Database: `~/.icarus/icarus.db` (SQLite)
     - Logs: `~/.icarus/logs/` (rotating files: `cli.log`, `audit.jsonl`)

2. **Credential Resolution Order**:
   - Hierarchical resolution to ensure flexibility across local interactive development, headless environments, and CI:
     1. Command line argument (`--api-key`)
     2. Environment variables (`XAI_API_KEY`, `OPENROUTER_API_KEY`, `ICARUS_API_KEY`, etc.)
     3. OS Keyring (`keyring.get_password("icarus", provider)`)
     4. Clear diagnostic prompt / error when missing, never crashing silently or leaking keys.

3. **Session Behavior**:
   - `icarus chat` starts a new session by default.
   - Users can explicitly resume previous sessions via `--resume` (resumes latest) or `--session <id>`.

4. **Database Lifecycle & Migrations**:
   - SQLAlchemy 2 models define core entities (`SessionModel`, `MessageModel`, `AgentRunModel`) from Day 1.
   - Alembic manages migrations, which execute automatically on CLI startup (`icarus init`, `icarus doctor`, `icarus chat`) so users always have an up-to-date schema without manual steps.

5. **uv Workspace Scaffolding**:
   - Root `pyproject.toml` targeting Python `>=3.12`.
   - Scaffold the three core packages needed for Phase 0/1 immediately:
     - `packages/contracts` (`icarus_contracts`)
     - `packages/agent-core` (`icarus_core`)
     - `apps/cli` (`icarus_cli`)
   - Reserve `apps/api`, `apps/worker`, and `apps/desktop` for subsequent phases.

6. **Hybrid Provider Strategy**:
   - Architecture: Direct BYOK + `ModelProvider` abstraction protocol + OpenRouter + LiteLLM as an optional gateway/SDK.
   - **Primary Development Provider**: Grok / xAI (`grok-2`, `grok-beta`) via direct SDK/REST integration.
   - **Multi-Model Aggregator**: OpenRouter as a first-class supported provider allowing single-key access to hundreds of models.
   - **LiteLLM**: Used as an adapter where its gateway, failover routing, or proxy capabilities provide leverage, without hardcoding all core logic to LiteLLM.

## Consequences
- Clean separation between provider interfaces and provider implementations.
- No vendor lock-in to LiteLLM or any single provider.
- End-user local setup is friction-free with automatic migrations and predictable `~/.icarus/` configuration.
