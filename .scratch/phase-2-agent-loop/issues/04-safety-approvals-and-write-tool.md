# 04: Human-in-the-Loop Safety Approvals and Workspace Modification (write_file)

**What to build:** An approval policy engine and interactive terminal approval prompt (`[y/N]`) that guards destructive operations. Implement the `write_file` tool to create or overwrite workspace files within `cwd`. When a write tool is requested, the CLI displays a styled Rich panel showing the target path and action preview. If the user accepts, the write executes; if the user rejects, a rejection message is returned to the model without crashing the session. Supports an `--auto-approve` / `-y` flag to bypass interactive prompts in automated/scripted runs.

**Blocked by:**
- 02: Tool Contracts and Read-Only Filesystem Tools (read_file, list_dir)

**Status:** ready-for-agent

- [ ] Approval engine implemented under `icarus_core.agent.approvals` supporting `INTERACTIVE`, `AUTO_APPROVE`, and `DENY` policies.
- [ ] `write_file` tool implemented with path resolution, workspace jailing, directory auto-creation, and content writing.
- [ ] Marked as `REQUIRES_APPROVAL` in the tool definition.
- [ ] Interactive terminal prompt in `apps/cli` displays styled action preview and collects `[y/N]` confirmation.
- [ ] `--auto-approve` / `-y` flag supported in `icarus run` and `icarus chat`.
- [ ] Unit and CLI tests verify write execution upon approval, clean refusal on user denial, and workspace escape rejection.
