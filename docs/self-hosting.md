# Icarus Self-Hosting & Remote CLI Guide

This guide details how to deploy and manage a self-hosted instance of the **Icarus AI Agent Platform** using Docker Compose, PostgreSQL, FastAPI, autonomous background workers, and Caddy reverse proxy, as well as how to configure and use the remote CLI client.

---

## 1. Architecture Overview

A complete self-hosted Icarus deployment consists of four coordinated components:

```
                      ┌──────────────────────┐
                      │     Icarus CLI       │
                      │ (Developer Machine)  │
                      └──────────┬───────────┘
                                 │ HTTPS / SSE
                                 ▼
                      ┌──────────────────────┐
                      │     Caddy 2 Proxy    │
                      │   (Port 80 / 443)    │
                      └──────────┬───────────┘
                                 │
                 ┌───────────────┴───────────────┐
                 ▼                               ▼
       ┌───────────────────┐           ┌───────────────────┐
       │   FastAPI Server  │           │ Background Worker │
       │   (`apps/api`)    │           │  (`apps/worker`)  │
       └─────────┬─────────┘           └─────────┬─────────┘
                 │                               │
                 └───────────────┬───────────────┘
                                 │ SQL (QueuePool)
                                 ▼
                      ┌──────────────────────┐
                      │  PostgreSQL Database │
                      │   (Version 16+)      │
                      └──────────────────────┘
```

1. **FastAPI Server (`apps/api`)**: High-performance HTTP/SSE API service handling authentication, session transcripts, tool streaming, and agent execution.
2. **Background Worker (`apps/worker`)**: Autonomous daemon polling and executing scheduled background jobs with atomic `FOR UPDATE SKIP LOCKED` claims.
3. **PostgreSQL Database**: Persistent storage for tenant-scoped sessions, messages, execution runs, and scheduled jobs.
4. **Caddy Reverse Proxy**: Automatic TLS certificate provisioning, security headers, and unbuffered SSE event stream proxying (`flush_interval -1`).
5. **Remote CLI (`apps/cli`)**: Local developer interface connected to the remote deployment, streaming tokens and execution telemetry with 100% parity to local runs.

---

## 2. Quickstart with Docker Compose

### Prerequisites
- Docker (24.0+) & Docker Compose (v2.20+)
- Git

### Launching the Stack
1. Clone the repository and enter directory:
   ```bash
   git clone https://github.com/AchillesLabs/icarus-agent.git
   cd icarus-agent
   ```

2. Start all services in the background:
   ```bash
   docker compose up -d --build
   ```

3. Verify service health:
   ```bash
   curl http://localhost/health
   # Returns: {"status":"healthy","version":"0.1.0","storage":{"status":"healthy","engine":"postgresql"}}
   ```

4. View service logs:
   ```bash
   docker compose logs -f api
   docker compose logs -f worker
   ```

---

## 3. Environment Variables Reference

Configure environment settings in `docker-compose.yml` or an `.env` file:

| Variable | Description | Default | Example |
| :--- | :--- | :--- | :--- |
| `ICARUS_DATABASE_URL` | SQLAlchemy connection URL for PostgreSQL | `sqlite:///...` | `postgresql+psycopg://user:pass@host:5432/icarus` |
| `ICARUS_AUTH_ENABLED` | Toggle Bearer authentication requirement | `true` | `true` / `false` |
| `ICARUS_API_KEYS` | Comma-delimited list of `token:tenant_id` pairs | `""` | `sk-prod-key:org_corp,sk-dev-key:dev_team` |
| `ICARUS_DEFAULT_PROVIDER` | Default LLM provider for runs | `groq` | `groq`, `openrouter`, `grok`, `mock` |
| `ICARUS_DEFAULT_MODEL` | Default model identifier | Provider default | `openai/gpt-oss-120b`, `anthropic/claude-3.5-sonnet` |
| `ICARUS_CORS_ORIGINS` | Allowed CORS origins (comma-delimited) | `*` | `https://dashboard.example.com` |
| `ICARUS_LOG_LEVEL` | Logging verbosity level | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` |

---

## 4. Database Migrations

Database schema migrations are managed via Alembic.

To apply pending migrations to the PostgreSQL database inside Docker:
```bash
docker compose exec api uv run alembic upgrade head
```

Or from your local development environment:
```bash
ICARUS_DATABASE_URL="postgresql+psycopg://icarus:icarus_secret@localhost:5432/icarus" uv run alembic upgrade head
```

---

## 5. Remote CLI Profile Management

The `icarus server` command suite manages remote connection profiles stored in `~/.icarus/config.toml` with credentials saved securely in the OS keyring.

### Adding a Remote Server Profile
```bash
# Add a remote profile and set it as active
icarus server add production https://api.icarus.example.com --key sk-icarus-admin-key

# Add a staging profile without activating it
icarus server add staging https://staging.icarus.example.com --key sk-icarus-demo-key --no-activate
```

### Listing Configured Server Profiles
```bash
icarus server list
```
Output:
```
                     Configured Remote Icarus Servers                     
┏━━━━━━━━━━┳━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━┓
┃  Status  ┃ Name       ┃ URL                             ┃ Auth         ┃
┡━━━━━━━━━━╇━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━┩
│  ACTIVE  │ production │ https://api.icarus.example.com  │ Token Set    │
│ inactive │ staging    │ https://staging.icarus.example… │ Token Set    │
└──────────┴────────────┴─────────────────────────────────┴──────────────┘
```

### Switching Active Remote Server
```bash
icarus server switch staging
```

### Removing a Profile
```bash
icarus server remove staging
```

---

## 6. Remote CLI Execution Parity

When an active remote server profile is configured, or when passing the `--remote` flag, `icarus run`, `icarus chat`, `icarus sessions`, and `icarus history` execute against the remote API server.

### One-Shot Query Execution (`icarus run`)
Tokens stream in real-time and Rich execution summary panels display upon completion:
```bash
# Runs against the active remote server profile
icarus run "Analyze the latest deployment status"

# Explicitly target a specific server profile
icarus run "Check logs" --server production

# Force local execution even if a remote profile is active
icarus run "Local query" --local
```

### Interactive Chat REPL (`icarus chat`)
Launches the full interactive REPL session connected to the remote API server:
```bash
# Start a new remote chat session
icarus chat

# Resume the most recent remote chat session
icarus chat --resume

# Load a specific remote session by UUID
icarus chat --session <session-id>
```

### Remote Session Inspection (`icarus sessions` & `icarus history`)
Inspect previous conversation threads and transcripts stored in the remote PostgreSQL database:
```bash
# List remote conversation sessions
icarus sessions

# Inspect full chronological transcript of a remote session
icarus history <session-id>
```
