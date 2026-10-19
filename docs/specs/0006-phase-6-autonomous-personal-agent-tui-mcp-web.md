# Spec 0006: Phase 6 - Autonomous Personal Agent, Full-Screen TUI Workspace, Web Search, Official MCP Servers (Browser & Booking), and Background Reminders

- **GitHub Issue**: [#41](https://github.com/AchillesLabs/icarus-agent/issues/41)
- **Status**: ready-for-agent
- **Target**: Phase 6 of Icarus Agent Architecture Roadmap
- **Estimated Scope**: Full-screen immersive terminal user interface (TUI) taking over the terminal window (like Claude Code) with pinned status headers and clean exit restoration, native live web search and webpage extraction tools, Model Context Protocol (MCP) client subsystem connecting to official MCP servers (Puppeteer/Playwright browser automation for clicking and booking, Google Maps, Fetch), CLI MCP server management (`icarus mcp`), natural language background reminders and task scheduling wired to the Phase 4 worker daemon, desktop notifications, and unified single-package PyPI/script distribution.

---

## Problem Statement

While Phases 1 through 5 delivered a rock-solid, multi-tenant agent runtime, background scheduler, and encrypted credential vault, the agent currently lacks real-world sensory and interactive capabilities to act as a true personal executive assistant (Chief of Staff / Jarvis):

1. **Terminal Clutter & Lack of Immersive Experience**: The CLI currently prints sequential text into the standard terminal scrollback. Unlike modern terminal applications (such as Claude Code), it does not take over the terminal in an alternate screen buffer, lacks pinned status bars for active models and token budgets, and does not provide an app-like focused environment.
2. **Zero Internet & Web Access**: The agent is restricted to local filesystem and shell commands. It cannot search the live internet for flight prices, hotel availability, restaurant reservations, current news, or documentation.
3. **Inability to Interact with Real Websites (Booking & Form-Filling)**: To act as a true assistant that books tickets, schedules reservations, or fills forms, the agent needs browser automation (navigating pages, clicking elements, filling inputs, taking screenshots).
4. **Isolated from Extensible Tool Ecosystems (MCP)**: Anthropic and the open-source community have standardized on the Model Context Protocol (MCP). Without an MCP client, Icarus cannot leverage official MCP servers for Puppeteer, Google Drive, Slack, GitHub, or custom services without writing bespoke code for each.
5. **Disconnected Personal Scheduling**: While a background database worker was built in Phase 4, users cannot naturally prompt the agent in chat to schedule tasks ("remind me at 6 PM to check hotel rates" or "monitor this page every 2 hours").
6. **Distribution Friction**: Users must currently clone the monorepo. Distributing the CLI requires packaging it into a single PyPI distribution (`uv tool install icarus-agent`) and providing universal one-line install scripts.

---

## Solution

Transform Icarus into a full-fledged Autonomous Personal Executive Agent equipped with an immersive full-screen terminal application, live web intelligence, official MCP server integrations for visual browser automation and booking, natural language background reminders, and seamless installation:

1. **Full-Screen Immersive Terminal Workspace (TUI)**: Launch into a dedicated alternate screen buffer taking over the terminal (like `claude`). Featuring a pinned top header bar (active model, token counters, session ID), a scrollable chat area with collapsible tool progress panels (browser actions, web searches), a bottom pinned status bar, and an interactive prompt with clean exit restoration.
2. **Native Live Web Search & Content Reader Tools**: Integrated real-time web search (DuckDuckGo / Brave) and clean URL content extraction enabling the agent to research current topics, check prices, and inspect websites without external dependencies.
3. **Model Context Protocol (MCP) Client Subsystem**: Connects to standard MCP servers via stdio and SSE transport. Discovers tools dynamically from servers (such as official Puppeteer/Playwright browser automation, Google Maps, or Slack) and binds them directly into the agent tool registry.
4. **CLI MCP Management Suite (`icarus mcp`)**: Commands to register, list, test, and remove MCP servers stored in `~/.icarus/mcp.json`.
5. **Natural Language Background Reminders & Scheduling**: Conversational scheduling tools allowing the agent to register one-off or recurring background jobs into the Phase 4 worker daemon, coupled with desktop notifications when tasks complete.
6. **Unified PyPI Packaging & Universal Installers**: Single `icarus-agent` package for PyPI (`uv tool install icarus-agent` / `pipx install icarus-agent`) and one-line installer scripts (`install.sh` and `install.ps1`).

---

## User Stories

1. As a user, I want `icarus` or `icarus chat` to launch into a full-screen terminal workspace, so that I have a clean, focused, application-like experience that takes over the terminal window like Claude Code.
2. As a user, I want the full-screen terminal to cleanly exit when I quit, so that my original shell history and prompt are restored without terminal pollution.
3. As a user, I want a pinned top status bar in the terminal workspace, so that I can monitor the active model, provider, session ID, and token usage at all times.
4. As a user, I want collapsible tool progress boxes in the chat view, so that I can see the agent's web searches and browser actions in real time without drowning in raw text.
5. As a user, I want a native `web_search` tool, so that the agent can search the live internet for flights, hotel prices, news, and answers to real-world questions.
6. As a user, I want a `fetch_webpage` tool, so that the agent can read and extract clean markdown content from any URL.
7. As a user, I want Icarus to connect to official MCP servers, so that I can give the agent browser automation, database access, and third-party tools with zero custom code.
8. As a user, I want an MCP browser automation tool (Puppeteer/Playwright), so that the agent can navigate to websites, click buttons, fill out booking forms, and find flight tickets autonomously.
9. As a user, I want to manage MCP servers using `icarus mcp add <name> <command>`, so that I can configure new tools from the terminal easily.
10. As a user, I want to run `icarus mcp list` and `icarus mcp test <name>`, so that I can verify that my connected MCP servers and their tools are operational.
11. As a user, I want to say "Remind me tomorrow at 9 AM to check flight prices", so that the agent schedules an autonomous task in the background worker.
12. As a user, I want to receive a system desktop notification when a background reminder or autonomous task completes, so that I am alerted even when my terminal is minimized.
13. As an external user, I want to install Icarus via `uv tool install icarus-agent` or `pipx install icarus-agent`, so that I can start using the assistant with a single command.
14. As a macOS or Linux user without Python, I want a `curl -fsSL https://... | sh` script, so that I can install Icarus automatically.
15. As a Windows user without Python, I want an `irm https://... | iex` script, so that I can install Icarus on Windows effortlessly.

---

## Implementation Decisions

### 1. Full-Screen Terminal Application (TUI)

- Implement a full-screen terminal application using prompt toolkit / alternate screen buffer mode (`\033[?1049h` / `\033[?1049l` or application session).
- Render a fixed header showing application name, active model, token counters, and active MCP servers.
- Render collapsible or bordered execution panels for active tool calls (web search progress, browser navigation steps).
- Ensure graceful exit restoring standard terminal screen buffers on `Ctrl+C` or `/exit`.

### 2. Native Live Web Search & Scraping Subsystem

- Implement a `web_search` tool providing multi-engine queries (DuckDuckGo HTML / Brave Search / SerpAPI fallback) returning structured results (title, snippet, URL).
- Implement a `fetch_webpage` tool extracting readable text from HTML with automatic boilerplate/script removal.
- Enforce request timeouts and response length limits to prevent token context blowup.

### 3. Model Context Protocol (MCP) Client Subsystem

- Construct an asynchronous MCP client supporting JSON-RPC 2.0 over standard I/O (`stdio`) child processes and Server-Sent Events (`sse`) transports.
- Implement server handshake and capability negotiation according to the MCP specification.
- Dynamically convert discovered MCP tool schemas into agent tool definitions and route executions back to the MCP process.

### 4. CLI MCP Server Configuration Management

- Store configured MCP servers in `~/.icarus/mcp.json`.
- Provide Typer CLI commands under `icarus mcp`: `add`, `list`, `test`, `remove`.
- Validate child process launch and schema discovery during `icarus mcp test`.

### 5. Conversational Scheduling & Desktop Notifications

- Add scheduling tools to the agent allowing natural language conversion of time expressions into scheduled job entries in the database.
- Wire task completions in the background worker to emit platform desktop notifications (using plyer, win10toast, or notify-py cross-platform).

### 6. Packaging & Universal Installation

- Consolidate packaging so `icarus-agent` installs the `icarus` command cleanly from PyPI.
- Write `install.sh` and `install.ps1` universal bootstrap scripts.

---

## Testing Decisions

### What Makes a Good Test

- Tests must exercise external contracts, MCP handshake JSON-RPC protocols, search tools, and scheduling triggers rather than internal variables.
- MCP client tests must verify process spawning, schema discovery, tool dispatch, and timeout handling against mock/standard stdio servers.
- Web search tests must handle mock HTTP payloads to ensure reliability without rate-limiting in CI.
- Scheduling tests must verify that conversational prompts correctly create database job rows with UTC timestamps.

### Modules Tested

- Full-screen terminal workspace layout and screen buffer transitions.
- Web search and webpage fetch tools.
- MCP client stdio transport, JSON-RPC protocol, and schema conversion.
- `icarus mcp` CLI management commands.
- Conversational scheduling tool and background worker execution.
- Packaging wheel build and installer scripts.

---

## Out of Scope

- Multi-agent swarm orchestration (Phase 10).
- Cross-platform desktop GUI with Tauri 2 (Phase 7).
- Cloud hosting deployment on AWS (Phase 8/9).
