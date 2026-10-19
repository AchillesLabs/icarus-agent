# 03: Model Context Protocol (MCP) Client Subsystem (stdio & SSE Transports)

**GitHub Issue:** [#51](https://github.com/AchillesLabs/icarus-agent/issues/51)
**Parent Spec:** [#41](https://github.com/AchillesLabs/icarus-agent/issues/41)

**What to build:** An asynchronous Model Context Protocol (MCP) client subsystem implementing JSON-RPC 2.0 communication over standard I/O (stdio child process) and Server-Sent Events (SSE) transports, performing standard MCP handshake, discovering remote tools dynamically, and converting MCP tool definitions into callable Icarus agent tools.

**Blocked by:** None (can start immediately)

**Status:** closed

## Acceptance criteria

- [x] Implement McpClient handling MCP JSON-RPC 2.0 lifecycle: initialize, ping, tools/list, and tools/call.
- [x] Implement StdioTransport spawning child process commands (e.g. npx -y @modelcontextprotocol/server-puppeteer) and communicating over stdin/stdout pipes.
- [x] Implement SseTransport connecting to remote HTTP/SSE MCP endpoints.
- [x] Dynamically map discovered MCP tool schemas into Icarus BaseTool instances with typed arguments and validation.
- [x] Handle MCP server crashes, execution timeouts, and protocol errors gracefully without crashing agent runtime.
- [x] Automated unit and mock integration tests verify handshake protocol, schema translation, tool execution round-trip, and error recovery.

