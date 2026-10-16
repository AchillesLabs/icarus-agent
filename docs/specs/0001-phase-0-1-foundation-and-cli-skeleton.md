# Spec 0001: Phase 0 & 1 - Monorepo Foundation, CLI Skeleton, and Hybrid Provider Runtime

## Problem Statement

Developers and power users currently lack a modular, open-source, CLI-first AI agent platform that can run completely locally on their workstation with zero external service dependencies, while also maintaining an extensible architecture that can seamlessly deploy to a self-hosted VPS, a managed multi-tenant cloud, or a cross-platform desktop app. Existing agent frameworks often suffer from tight vendor lock-in (e.g. hardcoding OpenAI APIs or single-provider SDKs), monolithic package structures that tightly couple web routing to core agent reasoning, unsafe credential handling (leaking plaintext keys in configuration files or logs), and lack of predictable token and execution boundaries. Users need a dependable, testable, CLI-first agent (`icarus`) that they can install with `uv`, configure with their own API keys (BYOK) using Grok, OpenRouter, or other providers, and run interactive or one-shot chats with local session persistence and strict safety controls.

---

## Solution

Build the Phase 0 and Phase 1 foundation of **Icarus-Agent**:
1. A modular Python 3.12+ monorepo managed with `uv` workspaces, dividing responsibilities into strictly bounded packages: shared contracts, core agent runtime (`icarus_core`), and the terminal client (`icarus_cli`).
2. An intuitive, robust Typer-based CLI command suite (`icarus init`, `icarus doctor`, `icarus chat`, `icarus run`, `icarus config`, `icarus logs`).
3. A flexible hybrid provider architecture featuring direct BYOK support (Grok / xAI as the primary development provider), native multi-model aggregation via OpenRouter, and LiteLLM integration where its unified gateway or failover routing is advantageous, all unified behind an internal `ModelProvider` protocol.
4. A secure credential resolution pipeline storing API keys in the OS keyring by default, with hierarchical environment variable overrides and graceful fallbacks for headless or CI environments.
5. Local persistence powered by SQLAlchemy 2 ORM from Day 1, managing SQLite session and run tables with automatic Alembic migrations applied seamlessly on startup under `~/.icarus/`.
6. Bounded, safe execution with path jail protections and approval policies prepared for subsequent tool-execution phases.

---

## User Stories

1. As a developer, I want to initialize the repository with `uv sync --all-packages`, so that all workspace dependencies and local packages are deterministically resolved from `uv.lock`.
2. As a CLI user, I want to run `icarus init`, so that the platform creates my local `~/.icarus/` configuration, initializes the SQLite database, and guides me through interactive provider setup.
3. As a CLI user, I want `icarus init` to securely prompt for my Grok (xAI) or OpenRouter API key and store it in my operating system's keyring, so that my secrets are never stored in plaintext on disk.
4. As a CLI user, I want to run `icarus doctor`, so that the system diagnoses my environment, tests my database connectivity, checks credential accessibility, and verifies provider reachability with actionable diagnostics.
5. As a developer in a CI or headless environment, I want to provide my credentials via environment variables (such as `XAI_API_KEY` or `ICARUS_API_KEY`), so that `icarus` executes without requiring an interactive desktop OS keyring daemon.
6. As a CLI user, I want to run `icarus chat`, so that I can have an interactive, streaming conversation with the agent directly in my terminal with Rich markdown formatting.
7. As a CLI user, I want `icarus chat` to create a fresh, isolated conversation session by default, so that new conversations start with a clean context window.
8. As a CLI user, I want to run `icarus chat --resume`, so that I can automatically continue my most recent conversation without needing to remember its session ID.
9. As a CLI user, I want to run `icarus chat --session <id>`, so that I can switch back to any previously created conversation thread.
10. As a CLI user, I want to run `icarus run "Prompt"`, so that I can execute a non-interactive one-shot query from scripts or pipes and receive output on stdout with clean exit codes.
11. As a CLI user, I want streaming model output to display progressively in the terminal as tokens arrive, so that I experience low-latency interactive responsiveness.
12. As a CLI user, I want model errors (such as HTTP 429 rate limits, invalid keys, context length exhaustion, or network disconnects) to be normalized into clear, human-readable terminal alerts rather than raw Python stack traces.
13. As a developer, I want `icarus_core` to be completely decoupled from CLI and web presentation frameworks, so that the exact same runtime can be reused in future server (`apps/api`) and desktop sidecar (`apps/desktop`) phases.
14. As a developer, I want all data transfer schemas and runtime events to be defined as typed Pydantic v2 models in a shared contracts package, so that domain boundaries remain strictly validated.
15. As a CLI user, I want my conversation sessions and messages to be persisted in a local SQLite database (`~/.icarus/icarus.db`) via SQLAlchemy 2, so that my chat history survives terminal restarts.
16. As a CLI user, I want database migrations to execute automatically during CLI startup, so that upgrading `icarus` to a new release never requires manual SQL or migration commands.
17. As a security-conscious user, I want all CLI and core logs to automatically redact API keys, authorization tokens, and private credential values, so that diagnostic logs can be shared safely.
18. As a developer, I want to configure `OPENAGENT_LOG_DIR` or `ICARUS_LOG_DIR` and log level (`DEBUG`, `INFO`), so that I can inspect rotating log files during local debugging.
19. As a user, I want to run `icarus config list` and `icarus config set <key> <val>`, so that I can easily view and tune model parameters (temperature, model name, default provider) without manually editing TOML files.
20. As a user, I want `icarus init` to let me choose OpenRouter as an alternative provider, so that I can access diverse foundation models using a single unified API key.
21. As a developer, I want an offline mock provider implementation conforming to `ModelProvider`, so that the full CLI and runtime test suite runs in CI without consuming real external API credits.
22. As a user, I want Ctrl+C during a streaming chat response to gracefully interrupt model generation without corrupting the session history or database.
23. As a CLI user, I want to type special slash commands within the chat REPL (e.g., `/exit`, `/clear`, `/help`, `/session`), so that I can manage my active chat context without leaving the session.

---

## Implementation Decisions

### Architectural Seams and Package Boundaries
- **Contracts Module**: Owns all shared Pydantic v2 schemas, DTOs, message types, session summaries, run status enums, and event envelopes. It has zero dependencies on other workspace packages.
- **Agent Core Module**: Owns the internal `ModelProvider` abstract protocol, provider registry, configuration managers, SQLAlchemy 2 ORM entities, repository interfaces, logging redaction utilities, and the bounded runtime loop. It strictly forbids imports of presentation code (FastAPI, Typer, Click).
- **CLI Module**: Owns the Typer application tree, Rich terminal formatters, REPL input handlers, and command actions (`init`, `doctor`, `chat`, `run`, `config`, `logs`). It depends on the contracts and agent-core modules.

### Hybrid Provider Abstraction
- The `ModelProvider` protocol defines typed asynchronous methods for generation, streaming token events, and exposing model capability metadata (max context tokens, tool-calling support, vision support).
- Direct provider adapters are built for Grok (`xai`) using modern REST/SDK interfaces.
- An OpenRouter adapter is built using standard OpenAI-compatible API specifications, enabling multi-model BYOK via OpenRouter keys.
- A LiteLLM adapter is implemented as an alternative backend, wrapping LiteLLM's router/completion calls behind the standard `ModelProvider` protocol.
- Provider errors are caught and normalized into domain exception types (e.g. `AuthenticationError`, `RateLimitError`, `ContextLengthExceededError`, `ProviderUnavailableError`).

### Credential Resolution Pipeline
- Credentials resolve through a fixed hierarchical pipeline:
  1. Explicit CLI arguments / flags (`--api-key`).
  2. Standard environment variables (`XAI_API_KEY`, `OPENROUTER_API_KEY`, `ICARUS_API_KEY`).
  3. Operating system credential store via `keyring`.
  4. Structured diagnostic error instructing the user how to configure their key if none is found.
- Plaintext API keys are strictly excluded from configuration files written to disk.

### Local Persistence & Migration Strategy
- Local storage is centralized under `~/.icarus/`:
  - Configuration: `~/.icarus/config.toml`
  - SQLite database: `~/.icarus/icarus.db`
  - Rotating logs: `~/.icarus/logs/cli.log`
- Core database entities (`SessionModel`, `MessageModel`, `AgentRunModel`) are defined using SQLAlchemy 2 declarative mapped models.
- Alembic configuration is embedded in `icarus_core`. An internal migration runner checks current revision against head and applies pending migrations automatically upon CLI initialization and command startup.

### Interactive UX & Terminal REPL
- `icarus chat` launches an interactive REPL using Rich for styled input prompts and live streaming markdown rendering.
- Each chat invocation creates a new persistent session record in SQLite unless `--resume` (or `--session <id>`) is explicitly supplied.
- Chat session handles SIGINT / Ctrl+C cleanly to abort generation without terminating the REPL loop.

---

## Testing Decisions

### What Makes a Good Test
- Tests must verify external behavior and observable contracts, not internal implementation details or private methods.
- Tests must run completely offline without requiring real internet access or live LLM provider credits.
- Tests should exercise the system at the highest architectural seam possible.

### Modules Tested
1. **CLI Commands via `CliRunner` (Highest Seam)**:
   - `icarus init`: Tests config file generation and mock keyring interaction.
   - `icarus doctor`: Tests health diagnostics against mock healthy and degraded dependencies.
   - `icarus chat`: Tests full interactive REPL turns, message persistence, and session resumption using a mock `ModelProvider`.
   - `icarus run`: Tests non-interactive command execution, output streaming to stdout, and exit codes on success and provider failure.
2. **Provider Abstraction Seam**:
   - Verification of `ModelProvider` implementations (Grok, OpenRouter, Mock) against standard protocol conformance, streaming chunks, and error normalization.
3. **Storage & Migrations Seam**:
   - Testing SQLAlchemy 2 session and message repositories against SQLite in-memory and temp file databases, verifying ACID transactions and automatic Alembic migration execution.
4. **Credential Resolution Seam**:
   - Testing priority order between CLI flags, environment variables, and mocked keyring backends.
5. **Redaction & Logging Seam**:
   - Automated tests asserting that string patterns matching API keys (e.g., `xai-...`, `sk-or-...`) are replaced with `[REDACTED]` before writing to log handlers.

### Prior Art
- CLI testing follows standard Typer/Click `CliRunner` patterns with Rich console capture.
- Repository tests follow established SQLAlchemy 2 session fixture patterns.

---

## Out of Scope

- Remote FastAPI HTTP server (`apps/api`), multi-tenant PostgreSQL, and Docker Compose deployment (scheduled for Phase 4).
- Background worker daemon (`apps/worker`), durable reminders, and PostgreSQL `SKIP LOCKED` queues (scheduled for Phase 4).
- LangGraph graph-based tool cycles, tool execution registry, and human-in-the-loop tool approvals (scheduled for Phase 2).
- Cross-platform desktop application using Tauri 2 and Python sidecar (scheduled for Phase 7).
- Multi-agent swarms, public plugin marketplaces, or web browser interfaces.

---

## Further Notes

- All code must pass `ruff check .`, `ruff format --check .`, and static type checking (`mypy` or `pyright`).
- Python version constraint is `>=3.12`.
- Directory structure for `apps/api`, `apps/worker`, and `apps/desktop` will be reserved in the repository layout but remain excluded from active build requirements until their respective phases.
