# 05: Interactive Chat REPL with Session Persistence

**What to build:** Build the primary interactive terminal experience: `icarus chat`. Users launch `icarus chat` to enter an interactive REPL with live streaming markdown output rendered via Rich. User inputs and assistant responses are committed to SQLite via the repository. Each chat starts a new session by default; users can resume the latest session with `--resume` or select an existing thread with `--session <id>`. Supports in-chat slash commands (`/exit`, `/clear`, `/help`, `/session`), handles Ctrl+C gracefully without corrupting state, and displays normalized provider error messages.

**Blocked by:**
- 02: Storage Engine and Automatic Migrations Tracer Bullet
- 03: Credential Resolution Pipeline and Interactive Configuration
- 04: Hybrid ModelProvider Protocol with Grok and Mock Adapters

**Status:** ready-for-agent

- [ ] `icarus chat` command implemented using Typer and Rich Live display for progressive token streaming.
- [ ] Session lifecycle managed in SQLite: new session created by default; `--resume` loads the latest session; `--session <id>` loads a specific thread.
- [ ] REPL slash commands implemented (`/exit`, `/clear`, `/help`, `/session`).
- [ ] SIGINT (Ctrl+C) during generation interrupts the stream without terminating the REPL loop or corrupting the database.
- [ ] Provider errors (e.g. rate limit, bad auth) are displayed as friendly terminal panels without stack traces.
- [ ] End-to-end tests using `CliRunner` and `MockProvider` verify multi-turn conversations and session resumption.
