# 01: Monorepo Foundation and Health Doctor Tracer Bullet

**What to build:** Establish the Python 3.12+ monorepo managed with uv workspaces containing `packages/contracts`, `packages/agent-core`, and `apps/cli`. Deliver a runnable `icarus` CLI binary providing `icarus --version` and `icarus doctor` to validate environment readiness (Python interpreter version, workspace integrity, logging directory creation). Configure Ruff linting/formatting and Pytest runner in CI.

**Blocked by:** None (can start immediately)

**Status:** closed

- [x] Root `pyproject.toml` configures a uv workspace with Python >=3.12 and locked dependencies.
- [x] Workspace packages `icarus_contracts`, `icarus_core`, and `icarus_cli` are scaffolded with correct dependency boundaries (core and contracts never import CLI).
- [x] `icarus --version` and `icarus --help` output correct version and command summaries using Typer and Rich.
- [x] `icarus doctor` runs basic environment checks (Python version, config directory, workspace health) and reports status cleanly.
- [x] `uv run pytest` executes the test suite with 100% pass rate.
- [x] `uv run ruff check .` and `uv run ruff format --check .` pass cleanly.
