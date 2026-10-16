# ADR 0002: Project Identity, Phase 0/1 Scope, Primary Provider, and Security Approvals

- **Status**: Accepted
- **Date**: 2026-10-16
- **Context**: Resolving Round 1 grilling decisions for Icarus-Agent based on `docs/proj_arch.docx`.

## Decisions

1. **Project Identity & Command Naming**:
   - The CLI binary is named `icarus` (e.g. `icarus init`, `icarus doctor`, `icarus chat`, `icarus run`).
   - Monorepo package namespaces:
     - `packages/contracts` &rarr; `icarus_contracts`
     - `packages/agent-core` &rarr; `icarus_core`
     - `apps/cli` &rarr; `icarus_cli`
     - `apps/api` &rarr; `icarus_api`
     - `apps/worker` &rarr; `icarus_worker`

2. **Immediate Build Milestone (Phases 0 & 1)**:
   - The initial planning spec and implementation tickets focus on **Phase 0 & Phase 1**:
     - Monorepo foundation managed by `uv` workspaces with committed `uv.lock`.
     - Shared contracts (`icarus_contracts`).
     - CLI commands: `init`, `doctor`, `chat`, `run` skeleton.
     - `ModelProvider` abstraction protocol with mocked offline test suite and active integration.
     - Storage: SQLAlchemy 2 models and SQLite repository configured from Day 1.
     - OS Keyring credential resolution with safe fallback.

3. **Provider Strategy**:
   - **Primary development provider**: Grok (`xai` models via LiteLLM).
   - **Multi-provider BYOK**: Users can select alternative providers (OpenAI, Anthropic, Google Gemini, Ollama) and configure their own API keys via `icarus init` or `icarus config`.

4. **Persistence Strategy**:
   - SQLAlchemy 2 ORM is adopted from Day 1 in Phase 1, using SQLite for local single-user mode. Repository patterns will be identical across SQLite and future PostgreSQL implementations. Alembic migrations manage schema versioning.

5. **Tool Execution Permissions & Workspace Boundaries**:
   - **Workspace Jailing**: Filesystem tools operate within the current working directory (`cwd`) by default. Any attempt to access or modify paths outside `cwd` requires explicit interactive user confirmation.
   - **Write Approval Policy**: By default, the agent asks for interactive user confirmation (`[y/N]`) before executing write operations (file write/delete, shell execution). Users may configure an auto-approve policy or elevated trust levels per workspace/session.

## Consequences
- Single CLI brand identity (`icarus`) aligns with the repository name.
- Building the ORM and repository abstraction from Day 1 avoids tech debt when transitioning to client-server mode later.
- Workspace jailing and approval defaults ensure security against accidental file modification or prompt injection.
