# Spec 0006: Phase 6 - Developer CLI Polish, Precision Code Editing, Interactive REPL, and PyPI Distribution

- **GitHub Issue**: [#41](https://github.com/AchillesLabs/icarus-agent/issues/41)
- **Status**: ready-for-agent
- **Target**: Phase 6 of Icarus Agent Architecture Roadmap
- **Estimated Scope**: Precision search-and-replace code editing tool with syntax-highlighted colored terminal diff previews, advanced interactive REPL powered by a prompt toolkit engine with autocompletion dropdowns (@file, /commands), interactive slash command suite (/help, /clear, /compact, /diff, /undo, /commit, /model, /cost), context file and git diff mention resolution, edit approval workflows with rollback, unified PyPI package distribution for `icarus-agent`, and cross-platform one-line shell/PowerShell installer scripts.

---

## Problem Statement

With Phase 4 (FastAPI server, PostgreSQL persistence, and autonomous workers) and Phase 5 (security hardening, encrypted BYOK vault, token revocation, rate limiting, and audit logging) completed, the underlying agent runtime is robust, persistent, and secure. However, before the team can distribute the Icarus CLI to public developers and compete with modern coding assistants (such as Claude Code, Cursor, and Aider), several critical developer ergonomics and usability gaps remain:

1. **Destructive and Token-Wasteful File Editing**: The agent currently only possesses a `write_file` tool that overwrites entire files from scratch. When editing a 500-line source file, the model must re-generate every line of code, wasting hundreds of output tokens, introducing hallucinated deletions, and increasing completion latency. Developers lack a precise search-and-replace editing tool that modifies only target blocks.
2. **Missing Diff Previews and Edit Rollback**: When the agent modifies code, developers cannot inspect a colorized terminal diff of what changed before or after the edit is applied. There is no confirmation prompt (`[y/n/always/diff]`) to review code edits, and no `/undo` command to instantly revert a mistaken modification.
3. **Basic Terminal Input Experience**: The interactive chat REPL currently relies on simple standard input without syntax highlighting, multiline editing, or persistent history across sessions. Developers cannot easily paste multi-line code snippets or navigate previous prompt histories with arrow keys.
4. **Lack of Context Mentions and Autocompletion**: In modern AI developer tools, developers fluidly reference files and git state using `@filename` or `@git:diff`. In Icarus, developers must manually type full file paths and instruct the agent to run `read_file`, rather than having files automatically discovered, autocomplete-suggested, and injected into context.
5. **Absence of Interactive Slash Commands**: In the middle of an interactive session, developers cannot check token consumption (`/cost`), switch models dynamically (`/model`), manually compact conversation memory (`/compact`), view cumulative changes (`/diff`), or generate a git commit (`/commit`) without leaving the REPL.
6. **Complex Monorepo Installation and Distribution**: The repository is currently organized as a multi-package workspace with internal path dependencies. An external developer cannot simply run `pip install icarus-agent` or `uv tool install icarus-agent`. Distributing the CLI requires packaging it into a single, cohesive PyPI wheel and providing a one-line installer script (`curl` / `irm`) for developers without Python pre-configured.

---

## Solution

Transform Icarus into a developer-first coding assistant by delivering a precision code-editing subsystem, an advanced interactive REPL with autocompletion popups, a full suite of interactive slash commands, context file mentions, and frictionless PyPI/script distribution:

1. **Precision Code Editing Tool (`edit_file` / `replace_file_content`)**: An intelligent block replacement tool supporting exact and whitespace-tolerant snippet matching, syntax-highlighted colored terminal diff previews (`+` / `-`), edit confirmation workflows, and automatic backup snapshots for instant rollback.
2. **Prompt Toolkit REPL Engine**: Replace basic standard input with an advanced terminal engine supporting live autocomplete popup menus (typing `@` suggests repository files, typing `/` suggests slash commands), persistent cross-session command history, and smooth multi-line prompt editing.
3. **Context Mention Injection (`@file`, `@dir`, `@git:diff`)**: Automatically parse `@` syntax in user inputs, resolve workspace file paths with fuzzy matching, format file contents with token badges, and append them directly to the conversation turn.
4. **Interactive Slash Command Suite**:
   - `/help`: Display a searchable directory of interactive commands and shortcuts.
   - `/clear`: Clear terminal display and start a fresh conversation thread.
   - `/compact`: Trigger manual conversation context compaction with summary preview and token savings metrics.
   - `/diff`: Render cumulative uncommitted file changes made by the agent during the current session.
   - `/undo`: Revert the last file modification executed by the agent.
   - `/commit`: Automatically generate a structured Conventional Commit message and commit staged changes to git.
   - `/model`: Switch active model or model provider on the fly without exiting the session.
   - `/cost`: Display real-time session token counters, turn metrics, and estimated API spend.
5. **Unified PyPI Package and One-Line Installer**: Package `icarus-agent` as a single, installable distribution on PyPI exposing the `icarus` executable command, with optional server extras (`icarus-agent[server]`), accompanied by universal installer scripts (`install.sh` for macOS/Linux and `install.ps1` for Windows).

---

## User Stories

1. As a developer, I want the agent to use a precision search-and-replace tool, so that large files can be updated without wasting tokens or accidentally deleting unrelated code.
2. As a developer, I want to see a colorized terminal diff before an edit is applied, so that I can verify the agent's proposed changes at a glance.
3. As a developer, I want the CLI to prompt for confirmation (`[y/n/always/diff]`) before modifying files, so that I retain full control over my codebase.
4. As an automated user, I want a `--auto-approve` (`-y`) flag, so that non-interactive scripts and trusted workflows apply file edits without pausing for confirmation.
5. As a developer, I want an `/undo` command in the REPL, so that I can instantly revert the agent's last file edit if the result was undesirable.
6. As a developer, I want a `/diff` command in the REPL, so that I can view all cumulative uncommitted modifications made during the active session.
7. As a developer, I want to type `@` in the chat prompt to see an autocomplete popup of files in my repository, so that I can reference files without typing long paths.
8. As a developer, I want to reference `@git:diff` in my prompt, so that the agent automatically inspects uncommitted repository changes without manual copy-pasting.
9. As a developer, I want to type `/` in the prompt to see a searchable list of slash commands with descriptions, so that I can discover and execute shortcuts effortlessly.
10. As a developer, I want persistent command history with up and down arrow navigation across CLI sessions, so that I can re-run previous prompts easily.
11. As a developer, I want multi-line prompt editing in the REPL, so that I can paste or write complex code blocks and formatted specifications.
12. As a developer, I want a `/commit` command, so that the agent can review my staged changes, propose a Conventional Commit message, and commit it to git on demand.
13. As a developer, I want a `/model` command, so that I can switch between fast/cheap models (e.g. Groq llama) and powerful reasoning models (e.g. Claude 3.5 Sonnet) mid-session.
14. As a developer, I want a `/cost` command, so that I can see the exact prompt tokens, completion tokens, turns, and estimated cost incurred during my session.
15. As a developer, I want a `/compact` command, so that I can summarize conversation history on demand when context budgets get high.
16. As a developer, I want a `/clear` command, so that I can reset terminal scrollback and start a fresh session without restarting the CLI.
17. As an external user, I want to install Icarus with `uv tool install icarus-agent` or `pipx install icarus-agent`, so that the CLI is added to my shell path in a single command.
18. As a user on macOS or Linux without Python installed, I want a `curl -fsSL https://... | sh` installer script, so that I can install and run Icarus without configuring Python environments manually.
19. As a Windows user without Python installed, I want a PowerShell `irm https://... | iex` installer script, so that I can install and run Icarus seamlessly on Windows.
20. As a self-hosting operator, I want server dependencies to be packaged as optional extras (`icarus-agent[server]`), so that CLI users do not have to download heavy PostgreSQL or FastAPI dependencies if they only want the local agent.
21. As a developer, I want `icarus doctor` to verify git installation, workspace boundaries, and terminal capabilities, so that diagnostic issues are highlighted proactively.
22. As a user, I want the CLI to remember my active server profiles and local settings in `~/.icarus/config.toml`, so that configuration is preserved across updates.
23. As a developer, I want syntax highlighting on file edits in the diff preview matching the programming language of the target file, so that diffs are easy to read.
24. As a developer, I want fuzzy whitespace matching in file replacements, so that minor indentation differences between LLM output and source code do not cause edit failures.
25. As a developer, I want `icarus chat` to display clean token badges next to user and assistant messages, so that I can track token growth during conversation turns.

---

## Implementation Decisions

### 1. Precision Code Editing Tool Subsystem

- Construct an `edit_file` tool registered alongside standard filesystem tools.
- Implement fuzzy block replacement: locate target content using exact match first, falling back to whitespace-normalized matching to tolerate minor indentation variations.
- Implement automated backup snapshots prior to file writing, stored in an in-memory or transient undo stack to enable instant rollback.
- Render colored terminal diff previews using standard unified diff formatting (`+` in green, `-` in red) with syntax highlighting where applicable.
- Provide interactive confirmation prompts before applying edits in standard chat mode, while respecting global `--auto-approve` flags.

### 2. Prompt Toolkit Interactive REPL Engine

- Upgrade the interactive chat loop from standard console input to a dedicated terminal application engine.
- Implement a custom completer that:
  - Detects `@` prefix and fuzzy-matches file paths from the current workspace root, filtering out ignored directories (`.git`, `node_modules`, `__pycache__`, `.venv`).
  - Detects `/` prefix and displays available slash commands with descriptions.
- Enable persistent history tracking stored in the user profile directory (`~/.icarus/history`), allowing arrow navigation across sessions.
- Support multi-line input handling allowing natural line breaks for code snippets.

### 3. Context Mention Resolution

- Implement an input preprocessor that scans user prompts for `@filename` and `@git:diff` tokens.
- For `@filename` mentions: read the file, format it in a structured code block with language identifier, and inject it as contextual reference into the turn messages.
- For `@git:diff` mentions: invoke git diff in the workspace root and inject uncommitted changes into the prompt context.

### 4. Interactive Slash Commands Suite

- Implement a modular slash command dispatcher inside the REPL loop.
- Support core developer commands:
  - `/help`: Print rich table of commands, parameters, and keyboard shortcuts.
  - `/clear`: Clear terminal screen and reset turn history.
  - `/compact`: Trigger explicit memory compaction and display token reduction statistics.
  - `/diff`: Display all uncommitted git changes in the active workspace.
  - `/undo`: Pop the last file modification from the backup stack and restore the file to its previous state.
  - `/commit`: Ask the agent to analyze staged changes, generate a Conventional Commit message, and execute `git commit`.
  - `/model`: Interactively select and switch active model or provider.
  - `/cost`: Display cumulative session telemetry and estimated spend.

### 5. Packaging and Multi-Platform Distribution

- Consolidate root package structure so that `icarus-agent` can be built and published as a unified wheel on PyPI.
- Package core runtime and CLI entry points into the default installation (`icarus-agent`).
- Define server and worker dependencies as optional extras (`icarus-agent[server]`).
- Create universal one-line installer scripts:
  - `install.sh`: POSIX shell script installing standalone uv and running `uv tool install icarus-agent`.
  - `install.ps1`: PowerShell script installing uv and running `uv tool install icarus-agent` on Windows.
- Update CI release workflow to publish wheels to PyPI or GitHub Releases on release tags.

---

## Testing Decisions

### What Makes a Good Test

- Tests must exercise observable CLI behavior, tool execution, diff formatting, and command dispatching rather than mocking internal string buffers.
- File editing tests must test real disk modifications on temporary directories, verifying that unchanged lines are preserved, target lines are modified, and diffs are generated accurately.
- Undo tests must verify that rolling back an edit completely restores the original file content byte-for-byte.
- Prompt completer tests must verify that `@` file completions respect workspace boundaries and ignore hidden directories (`.git`, `.venv`).
- Packaging tests must verify that the built wheel installs cleanly into an isolated virtual environment and exposes the executable `icarus` command on the system PATH.

### Modules Tested

- Precision file editing tool (`edit_file`) and block replacement logic.
- Diff generation, terminal formatting, and undo stack manager.
- REPL prompt toolkit completer and context mention preprocessor (`@file`, `@git:diff`).
- Interactive slash command handlers (`/help`, `/clear`, `/compact`, `/diff`, `/undo`, `/commit`, `/model`, `/cost`).
- Package wheel build, entry points, and installer script validation.

### Prior Art

- Phase 2 agent tool loop and filesystem tools (`tests/test_write_tool.py`, `tests/test_read_tools.py`, `tests/test_cli_approvals.py`).
- Phase 3 context budgeting and compaction (`tests/test_compactor.py`, `tests/test_chat_cli.py`).
- Phase 5 security CLI and server profile management (`tests/test_security_cli.py`, `tests/test_remote_cli.py`).

---

## Out of Scope

- Cross-platform desktop GUI application with Tauri 2 (planned for Phase 7).
- Full Model Context Protocol (MCP) server daemon integration (planned for Phase 8).
- Multi-region AWS deployment (retained as future cloud pilot milestone).
- Browser-based web chat application.

---

## Further Notes

- Phase 6 directly addresses the core feedback: making the CLI an indispensable, delightful daily driver for software engineers before investing in cloud hosting or desktop GUI layers.
- Preserves all remote server wiring developed in Phases 4 and 5: the CLI can still connect to local or remote servers via `icarus server` without modification.
