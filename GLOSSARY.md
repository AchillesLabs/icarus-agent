# Domain Glossary: Icarus-Agent

This glossary establishes the ubiquitous domain language for the project, aligning the CLI, API, worker, agent core, and future desktop applications.

---

### Core Execution & Runtime

- **Agent Core (`packages/agent-core` / `icarus_core`)**: The shared Python library housing agent logic, state management, LangGraph workflows, provider abstraction, tool execution, memory, and persistence interfaces. It never imports presentation layers (FastAPI, Typer).
- **Run (`agent_runs`)**: A bounded, typed unit of agent execution with an explicit lifecycle:
  `queued` &rarr; `running` &rarr; `waiting_for_approval` &rarr; `succeeded` | `failed` | `cancelled` | `expired`.
  Every run is constrained by hard budgets: max turns, max tool calls, wall-clock timeout, and token ceilings.
- **Session (`sessions`)**: A persistent conversation thread owned by an identity, containing an ordered history of messages and associated runs. In local CLI mode, a new session is created by default unless `--resume` or `--session <id>` is provided.
- **Context Budget**: The allocated token window calculated as:
  $$\text{budget} = \text{context\_window} - \text{output\_reserve} - \text{safety\_margin}$$
  Governs context assembly and triggers compaction before hard model limits are reached.
- **Compaction**: The process of summarizing older conversation history while preserving critical task goals, explicit user constraints, pending approvals, and unresolved tool outcomes.

---

### Deployment & Operating Modes

- **CLI (`apps/cli` / `icarus`)**: Typer-based command-line product invoked as `icarus` (e.g., `icarus init`, `icarus doctor`, `icarus chat`, `icarus run`).
- **Home Storage Directory (`~/.icarus/`)**: The standardized user data root across all platforms:
  - Configuration: `~/.icarus/config.toml`
  - Local Database: `~/.icarus/icarus.db`
  - Local Logs: `~/.icarus/logs/`
- **Local CLI Mode**: Standalone, single-user operation on the user's workstation. Runs `icarus_core` directly in-process; uses local SQLite for persistence and the OS keyring for credential storage without starting a network listener.
- **Self-Hosted VPS Mode**: Private client-server deployment via Docker Compose containing Caddy (TLS proxy), FastAPI (`apps/api` / `icarus_api`), durable worker (`apps/worker` / `icarus_worker`), and PostgreSQL. Controlled by a single owner/admin.
- **Managed AWS Mode**: Multi-tenant cloud hosting on AWS (pilot on EC2/Lightsail; scale via RDS, SQS, EventBridge, ECS). Enforces strict tenant isolation, server-side identity derivation, and quota controls.
- **Desktop Client (`apps/desktop`)**: Cross-platform desktop interface (Tauri 2 + React/TypeScript) that operates either by connecting to a remote FastAPI server or by managing a bundled local Python sidecar bound to `127.0.0.1` on an ephemeral port with an ephemeral handshake token.

---

### Models & Integrations

- **Model Provider Architecture**:
  - **Provider Protocol (`ModelProvider`)**: Internal abstract protocol defining standard methods (`generate`, `stream`, `get_capabilities`) and normalizing provider exceptions.
  - **Direct BYOK Adapters**: Native direct SDK/REST adapters for high-priority providers (Grok / xAI as primary development provider, Anthropic, OpenAI, Google Gemini, Ollama).
  - **Aggregator & Gateway Adapters**: First-class support for OpenRouter (multi-model aggregation via a single key) and LiteLLM where its unified gateway or proxy features are beneficial.
- **Credential Resolution Precedence**:
  1. CLI parameter / flag (`--api-key`)
  2. Environment variables (`XAI_API_KEY`, `OPENROUTER_API_KEY`, `ICARUS_API_KEY`, etc.)
  3. OS Keyring (`keyring.get_password("icarus", provider)`)
  4. Graceful failure / diagnostic report in headless environments without crashes.
- **Tool Runtime**: The execution sandbox enforcing Pydantic argument validation, execution timeouts, output size ceilings, and approval gates. External data (web, files, emails) is treated as untrusted input.
- **Workspace Jail & Path Boundaries**: Filesystem tools operate within the current working directory (`cwd`) by default. Any read or write access targeting files outside `cwd` requires explicit interactive user confirmation.
- **Trust Level / Auto-Approve Policy**: Configurable security policy for write operations (file write, delete, command execution). Default is `ask` (interactive `[y/N]` confirmation required before modifying files). Users can configure auto-approval rules or trust levels per workspace/session.
- **MCP Client Adapter**: An opt-in Model Context Protocol client supporting local `stdio` subprocesses (local mode only) and authenticated remote HTTP transports. Third-party MCP servers are never auto-trusted; tools require explicit allowlisting and approval policies.
- **First-Party OAuth Connectors**: Direct, least-privilege OAuth 2.0/PKCE connectors for high-value services (Gmail, Google Calendar, Google Drive, GitHub). Refresh tokens are encrypted and scoped to the authenticated owner.

---

### Persistence & Scheduling

- **Database Engine**: SQLAlchemy 2 ORM from Day 1. Backed by SQLite in local mode and PostgreSQL in server mode. Alembic migrations run automatically on CLI startup (`init`, `doctor`, `chat`) to ensure seamless upgrades without manual intervention.
- **Durable Job (`scheduled_jobs`)**: A persistent task record (e.g., reminder, recurring action) carrying an absolute UTC timestamp, original timezone, owner identity, idempotency key, and delivery target.
- **Worker / Scheduler (`apps/worker`)**: A background service that atomically claims due jobs from PostgreSQL (using `FOR UPDATE SKIP LOCKED`), enforces tenant permissions, and dispatches notifications independently of active client terminals.
- **Tenant Isolation**: Structural security invariant where all server-side operations derive `owner_id` exclusively from verified authentication credentials (never from client-supplied request payloads) and query scopes strictly enforce resource ownership.
