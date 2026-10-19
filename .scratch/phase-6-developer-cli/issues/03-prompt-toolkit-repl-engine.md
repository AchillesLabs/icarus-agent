# 03: Prompt Toolkit Interactive REPL Engine with Multi-Line and History

**GitHub Issue:** [#51](https://github.com/AchillesLabs/icarus-agent/issues/51)
**Parent Spec:** [#41](https://github.com/AchillesLabs/icarus-agent/issues/41)

**What to build:** Upgraded interactive terminal chat loop using prompt_toolkit, featuring persistent command history across sessions (stored in ~/.icarus/history with up/down arrow navigation), multi-line editing, and styled prompt formatting.

**Blocked by:**
- None (can start immediately)

**Status:** ready-for-agent

- [ ] Replace standard console.input() with prompt_toolkit.PromptSession in icarus chat loop.
- [ ] Enable persistent disk-backed command history in ~/.icarus/history across CLI sessions.
- [ ] Support multi-line prompt editing (Alt+Enter or auto-detecting open blocks/parentheses).
- [ ] Support keybindings (Ctrl+C to cancel current turn, Ctrl+D / exit to quit gracefully).
- [ ] Automated tests verify REPL input handling, history persistence, and exit signals.
