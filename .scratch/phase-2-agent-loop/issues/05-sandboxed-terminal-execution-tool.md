# 05: Sandboxed Terminal Execution Tool (run_command) with Timeout Controls

**What to build:** Tool enabling the agent to execute shell and terminal commands (e.g. running tests, linters, git commands, build scripts) with timeout budgets (default 30s) and stdout/stderr capture. Commands execute strictly within the workspace directory (`cwd`). Because shell commands are potentially destructive, they require explicit interactive user confirmation (`[y/N]`) unless `--auto-approve` / `-y` is enabled.

**Blocked by:**
- 04: Human-in-the-Loop Safety Approvals and Workspace Modification (write_file)

**Status:** ready-for-agent

- [ ] `run_command` tool implemented under `icarus_core.tools.command` executing subcommands asynchronously with shell selection based on OS (PowerShell/cmd on Windows, bash/sh on Unix).
- [ ] Enforces execution timeout budget (configurable, default 30.0s) and kills runaway processes cleanly.
- [ ] Captures combined stdout, stderr, and integer exit code into a structured result payload.
- [ ] Classifies `run_command` as `REQUIRES_APPROVAL`, prompting the user before execution.
- [ ] Unit tests verify successful command output, non-zero exit code reporting, timeout enforcement, and interactive approval rejection.
