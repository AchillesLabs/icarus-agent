# Icarus Agent

Modular, open-source, CLI-first AI agent platform.

## Architecture

- `packages/contracts`: Shared Pydantic schemas, DTOs, and event envelopes.
- `packages/agent-core`: Runtime engine, provider adapters, persistence, and execution sandbox.
- `apps/cli`: Typer + Rich terminal user experience (`icarus`).
- `apps/api`: (Reserved) FastAPI HTTP service with SSE streaming.
- `apps/worker`: (Reserved) Durable background scheduler daemon.
- `apps/desktop`: (Reserved) Cross-platform desktop interface.

## Quick Start

```bash
uv sync --all-packages
uv run icarus --help
uv run icarus doctor
```
