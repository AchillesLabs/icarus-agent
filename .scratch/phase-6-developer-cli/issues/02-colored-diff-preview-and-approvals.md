# 02: Colored Terminal Diff Preview and Edit Approval Workflow

**GitHub Issue:** [#50](https://github.com/AchillesLabs/icarus-agent/issues/50)
**Parent Spec:** [#41](https://github.com/AchillesLabs/icarus-agent/issues/41)

**What to build:** Syntax-highlighted unified diff previews rendered in the terminal before or after code edits, interactive confirmation prompts giving developers full control (Apply this edit? [y/n/always/diff]), and seamless integration with --auto-approve (-y).

**Blocked by:**
- #49 (01: Precision Search-and-Replace File Editing Tool (edit_file))

**Status:** ready-for-agent

- [ ] Implement unified diff generator comparing pre-edit and post-edit file states with Rich terminal syntax highlighting (+ in green, - in red).
- [ ] Present interactive confirmation prompt [y/n/always/diff] before writing modifications to disk in interactive chat mode.
- [ ] Bypass interactive confirmation prompts automatically when --auto-approve / -y is specified.
- [ ] Emit structured audit log events for approved, rejected, and automated file modifications.
- [ ] Automated tests verify diff rendering, approval prompt choices, and auto-approve behavior.
