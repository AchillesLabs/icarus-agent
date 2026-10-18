# 07: Execution Guardrails: Turn Limits, SQLite Tool Persistence, and Clean Cancellation

**What to build:** Enforce robust production guardrails on the autonomous agent loop: a hard maximum turn budget (default 25 turns) to prevent runaway loops or infinite tool recursions; complete persistence of tool calls and tool responses in the SQLite database (`role="tool"`) so that tool-assisted sessions can be resumed with full context preserved; and clean SIGINT / Ctrl+C cancellation during running tools or model reasoning without corrupting the session history or database.

**Blocked by:**
- 06: Autonomous Multi-Turn ReAct Execution Loop with Live UI Streaming

**Status:** closed

- [x] Hard turn limit enforcement (configurable in `config.toml`, default 25 turns) that halts loop with a clear user notice when reached.
- [x] Session database schema and repositories support persisting tool calls, tool responses, and call IDs in `MessageModel` with `MessageRole.TOOL`.
- [x] Session resumption (`icarus chat -r` or `icarus chat -s <id>`) cleanly reconstructs prior tool-turn history for resumed conversations.
- [x] SIGINT / Ctrl+C signal handling during tool execution or model streaming halts the current turn gracefully and saves partial session state without database corruption.
- [x] End-to-end integration tests verifying turn limit termination, tool message persistence and reload, and cancellation resilience.
