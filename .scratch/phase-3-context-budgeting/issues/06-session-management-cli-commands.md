# 06: Session Management CLI Commands (icarus sessions and icarus history)

**What to build:** Dedicated CLI commands and user interfaces for inspecting session history, transcripts, and token usage. `icarus sessions` lists previous conversations in a formatted Rich table showing session ID, title, mode, message count, estimated tokens, and last active timestamp. `icarus history <session_id>` outputs the full chronological transcript of a session with syntax highlighting for user prompts, model responses, tool calls, and token metrics. Displays an execution summary table at the end of runs.

**Blocked by:** 05: Run Telemetry Accumulation and SQLite Budget Persistence

**Status:** ready-for-agent

- [ ] Add `icarus sessions` command in `icarus_cli` with `--limit` option, rendering a styled Rich table of past sessions.
- [ ] Add `icarus history <session_id>` command displaying formatted message history, tool calls, tool results, and token estimates.
- [ ] Enhance session repository queries to aggregate session message counts, run counts, and token totals efficiently.
- [ ] Render a summary telemetry panel at the conclusion of `icarus run` showing turns, token usage, tool calls, and duration.
- [ ] CLI tests verify output formatting and error handling for nonexistent sessions.
