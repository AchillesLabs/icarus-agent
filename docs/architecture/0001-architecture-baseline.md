# ADR 0001: Architecture Baseline and Staged Implementation

- **Status**: Accepted
- **Date**: 2026-10-16
- **Context**: Product requirements and system architecture for OpenAgent / Icarus-Agent (`docs/proj_arch.docx`).

## Context and Problem Statement
We need an extensible, open-source, CLI-first AI agent platform that can run locally, deploy as a self-hosted VPS service, operate in a managed multi-tenant AWS cloud, and eventually support a cross-platform desktop application. We need clear package boundaries, reliable execution, strict tenant isolation, secure credential management (BYOK), and a staged roadmap without premature infrastructure complexity.

## Decisions

1. **Monorepo and Workspace Structure**:
   - Python 3.12+ monorepo managed with `uv` workspaces and a unified `uv.lock`.
   - Distinct packages with single-direction dependencies:
     - `packages/contracts`: Versioned Pydantic DTOs and event schemas.
     - `packages/agent-core`: Pure agent runtime, LangGraph state, provider adapters, tools, memory, and persistence interfaces. (Never imports FastAPI or Typer).
     - `apps/cli`: Typer + Rich terminal application.
     - `apps/api`: FastAPI HTTP service with SSE streaming and owner-scoped routes.
     - `apps/worker`: Daemon claiming durable jobs from PostgreSQL (`SKIP LOCKED`).
     - `apps/desktop` (Planned later phase): Tauri 2 + React/TypeScript with a bundled Python sidecar.

2. **Agent Runtime & Orchestration**:
   - Use LangGraph for graph state transitions, checkpoints, and interruptible workflows (human-in-the-loop approvals).
   - Wrap LangGraph in our own bounded runtime layer enforcing hard execution budgets (turn limits, tool limits, wall-clock timeouts, and context token ceilings).
   - Normalize LLM calls via an internal `ModelProvider` protocol, using LiteLLM for cloud models and direct endpoints for local inference (Ollama).

3. **Storage & Persistence**:
   - Local single-user mode uses SQLite.
   - Server mode (self-hosted & managed AWS) uses PostgreSQL with SQLAlchemy 2 and Alembic migrations.

4. **Security & BYOK (Bring Your Own Key)**:
   - Credentials in local CLI mode are stored in the OS keyring.
   - Credentials in server mode are stored envelope-encrypted at rest and decrypted only for the active, authorized run.
   - Never log keys, send them in prompts, or expose them across tenant boundaries.
   - Arbitrary shell execution is disabled by default in hosted mode.
   - Untrusted inputs (web pages, documents, tool outputs) are strictly prevented from overriding safety policies.

5. **Tooling & Extensibility**:
   - First-party OAuth connectors (Gmail, Google Calendar, Google Drive, GitHub) with least-privilege scopes.
   - Opt-in MCP client adapter for stdio (local mode) and authenticated HTTP (remote). Third-party servers are untrusted by default.

6. **Phased Build Order**:
   - Milestone 0: Workspace foundation and repo tooling.
   - Milestone 1: Local CLI and runtime skeleton with mocked/live single-model chat.
   - Milestone 2: Bounded LangGraph agent loop with tool registry and approval gates.
   - Milestone 3: Context management, token budgeting, history compaction, and SQLite persistence.
   - Milestone 4: FastAPI service, remote CLI profiles, PostgreSQL/Alembic, worker/scheduler, Docker Compose.
   - Milestone 5+: Security hardening, AWS pilot, desktop client.

## Consequences
- **Positive**: Clean separation of concerns allows the AI/runtime engineer and backend engineer to work without blocking each other. The core agent logic is reusable across CLI, server, and desktop.
- **Negative**: Managing dual database engines (SQLite vs. PostgreSQL) requires strict repository abstractions and testing across both backends.
