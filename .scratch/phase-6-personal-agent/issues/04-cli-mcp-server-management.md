# 04: CLI MCP Server Configuration Management (icarus mcp add/list/test/remove)

**GitHub Issue:** [#52](https://github.com/AchillesLabs/icarus-agent/issues/52)
**Parent Spec:** [#41](https://github.com/AchillesLabs/icarus-agent/issues/41)

**What to build:** CLI management suite under icarus mcp enabling users to configure, list, test, and remove MCP servers stored persistently in ~/.icarus/mcp.json, including test connection verification that spawns the server and inspects exposed tools.

**Blocked by:** #51 (03: Model Context Protocol (MCP) Client Subsystem)

**Status:** closed

## Acceptance criteria

- [x] Implement McpConfigManager managing persistent server definitions in ~/.icarus/mcp.json.
- [x] Implement icarus mcp add <name> <command> [args...] with optional environment variables and transport flags (--sse/--stdio).
- [x] Implement icarus mcp list displaying configured servers, transport types, and tool counts in a formatted Rich table.
- [x] Implement icarus mcp test <name> performing live handshake and printing discovered tools and schemas.
- [x] Implement icarus mcp remove <name> unregistering configured servers.
- [x] Auto-load configured MCP servers into agent runtime during CLI startup.
- [x] Automated integration tests verify config storage, CLI commands, and runtime discovery.

