# 06: Unified PyPI Wheel Packaging (icarus-agent) and One-Line Universal Installers (curl/irm)

**GitHub Issue:** [#54](https://github.com/AchillesLabs/icarus-agent/issues/54)
**Parent Spec:** [#41](https://github.com/AchillesLabs/icarus-agent/issues/41)

**What to build:** Consolidated single-package distribution on PyPI (icarus-agent) exposing the icarus executable CLI command with optional server extras (icarus-agent[server]), plus universal one-line installer scripts (install.sh for macOS/Linux and install.ps1 for Windows) enabling instant installation without manual Python setup.

**Blocked by:** #49, #50, #51, #52, #53

**Status:** closed

## Acceptance criteria

- [x] Configure pyproject.toml so icarus-agent builds as a single installable wheel exposing the icarus console script.
- [x] Define server and worker dependencies as optional extras under [project.optional-dependencies] server.
- [x] Create install.sh for macOS/Linux installing uv if needed and running uv tool install icarus-agent.
- [x] Create install.ps1 for Windows installing uv and running uv tool install icarus-agent.
- [x] Automated tests verify wheel build, clean venv installation, entry point execution, and installer script syntax.

