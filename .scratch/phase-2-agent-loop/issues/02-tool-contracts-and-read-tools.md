# 02: Tool Contracts and Read-Only Filesystem Tools (read_file, list_dir)

**What to build:** Shared Pydantic contracts for tool definitions, function calling schemas, tool requests, and tool results, alongside an extensible tool registry in `icarus_core`. Implement safe read-only filesystem tools (`read_file` with line slicing, `list_dir` for directory exploration) enforced with workspace jailing to current working directory (`cwd`). Verified end-to-end: provider adapters format tool schemas, agent executes tools within workspace boundaries, and tool results return clean structured data.

**Blocked by:**
- 01: Agent Persona and Dynamic System Instruction Injection

**Status:** ready-for-agent

- [ ] `ToolDefinition`, `ToolCall`, and `ToolResult` contracts defined in `icarus_contracts` with OpenAI-compatible function schema generation.
- [ ] Tool registry implemented under `icarus_core.tools.registry` managing registered tool instances and schema exports.
- [ ] `read_file` tool implemented with path resolution, boundary checks (workspace jailing), and optional line offset/limit slicing.
- [ ] `list_dir` tool implemented with path resolution, recursive depth control, and entry metadata (size, file/directory).
- [ ] Unit tests verify schema compliance, tool execution, and rejection of path traversals attempting to escape workspace boundaries.
