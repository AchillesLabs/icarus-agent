# 01: Full-Screen Immersive TUI Terminal Workspace with Alternate Screen Buffer and Pinned Status Bar

**GitHub Issue:** [#49](https://github.com/AchillesLabs/icarus-agent/issues/49)
**Parent Spec:** [#41](https://github.com/AchillesLabs/icarus-agent/issues/41)

**What to build:** An immersive full-screen terminal user interface (TUI) workspace taking over the terminal window (like Claude Code) using prompt_toolkit and alternate screen buffer mode (\033[?1049h), featuring a pinned top header bar (active model, provider, token counters, session ID), scrollable conversational stream with collapsible tool execution progress panels, bottom status bar, and clean terminal state restoration on exit.

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

## Acceptance criteria

- [ ] Launch icarus chat (or default icarus) into an alternate screen buffer taking over the full terminal window.
- [ ] Render pinned top header status bar displaying application name, active LLM model, provider, session ID, and token usage budget.
- [ ] Render collapsible or bordered tool execution panels in the message stream showing live progress for web search, browser automation, and MCP operations.
- [ ] Implement interactive prompt at the bottom of the screen with multiline input support, command history, and keybindings (Ctrl+C cancel turn, Ctrl+D / exit clean exit).
- [ ] Restore standard terminal screen buffer and original scrollback cleanly upon session exit without corrupting terminal state.
- [ ] Automated unit and integration tests verify screen buffer transition commands, header rendering, and graceful exit handling.
