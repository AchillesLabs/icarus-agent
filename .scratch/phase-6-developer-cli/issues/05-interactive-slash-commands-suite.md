# 05: Interactive Slash Command Suite (/help, /clear, /compact, /diff, /undo, /commit, /model, /cost)

**GitHub Issue:** [#53](https://github.com/AchillesLabs/icarus-agent/issues/53)
**Parent Spec:** [#41](https://github.com/AchillesLabs/icarus-agent/issues/41)

**What to build:** In-session slash command dispatcher allowing developers to execute essential workflow operations mid-chat: viewing help, clearing screen, compacting memory, reviewing cumulative changes, rolling back file edits (/undo), creating git commits (/commit), switching models on the fly (/model), and inspecting token spend (/cost).

**Blocked by:**
- #49 (01: Precision Search-and-Replace File Editing Tool (edit_file))
- #50 (02: Colored Terminal Diff Preview and Edit Approval Workflow)
- #51 (03: Prompt Toolkit Interactive REPL Engine with Multi-Line and History)

**Status:** ready-for-agent

- [ ] Implement slash command parser and dispatcher intercepting /<cmd> inputs before model generation.
- [ ] Provide slash command autocomplete popup when user types / in the prompt.
- [ ] Implement /help, /clear, /compact, /diff (git diff of session changes), /undo (reverting last file edit via undo stack), /commit (auto-generating commit message), /model, and /cost commands.
- [ ] Render formatted Rich panels and tables for slash command outputs.
- [ ] Automated integration tests verify each slash command handler, undo fidelity, and prompt interception.
