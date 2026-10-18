# Spec 0002: Phase 2 - Autonomous Agent Loop, Tool Registry, and Human-in-the-Loop Safety

- **Status**: Completed / Closed
- **Completion Date**: 2026-10-18
- **Target**: Phase 2 of Icarus Agent Architecture Roadmap
- **Verification**: 269 tests passing, all 7 tracer-bullet tickets verified and merged to `main`.

## Problem Statement

In Phase 1, `icarus` established a robust foundation for configuration, storage, credential security, provider adapters, and direct conversational chat. However, the model currently operates in a passive, standalone text mode without system instructions, environment awareness, or tool execution capabilities. It cannot inspect files, execute terminal commands, search the codebase, or autonomously solve engineering tasks. Furthermore, running unguided models without strict system instructions and safety boundaries can lead to prompt injection risks, training-data meme hallucinations, and dangerous unapproved disk or shell modifications. Users need an autonomous, dependable agent loop that can intelligently reason, call structured tools, respect workspace boundaries, ask for explicit confirmation before destructive actions, and operate with firm turn and token budgets.

---

## Solution

Build **Phase 2: Autonomous Agent Engine and Tool Execution Architecture** for Icarus Agent:
1. **Agent Persona & Dynamic System Prompt**: A structured system prompt builder that injects agent identity, behavior guidelines, OS environment details, current working directory, and tool-use instructions into model invocations.
2. **Typed Tool Contracts & Schema Registry**: Standardized Pydantic contracts for tool definitions, function calling schemas, tool calls, and tool results, with an extensible tool registry in `icarus_core`.
3. **Essential Core Tools**:
   - `read_file`: Inspect file contents with line offset controls.
   - `write_file`: Create or update files within workspace boundaries.
   - `list_dir`: Explore directory trees.
   - `search`: Search patterns across workspace files.
   - `run_command`: Execute terminal commands with timeout controls and stdout/stderr capture.
4. **Workspace Jailing & Security Approval Policies**: Enforce current working directory (`cwd`) jailing. Require interactive user confirmation (`[y/N]`) before executing write operations or shell commands, with an optional `--auto-approve` / `-y` override.
5. **Autonomous ReAct Execution Loop**: A multi-step reasoning and tool-execution loop that dispatches tool calls, formats tool outputs, streams progress in the CLI via Rich status panels, and continues until the task is complete.
6. **Execution Budget & Graceful Interruption**: Enforce configurable turn limits and timeout budgets, ensuring clean Ctrl+C cancellation without session corruption.

---

## User Stories

1. As a user, I want every conversation and run to inject a clear system prompt, so that the model understands it is Icarus Agent, follows safety guidelines, and does not hallucinate raw unguided memes.
2. As a user, I want the agent to know my environment context (OS, current working directory, git branch), so that it can give relevant, workspace-aware answers.
3. As a developer, I want all tools to be defined with standard JSON function schemas, so that any provider supporting tool-calling (Groq, OpenRouter, Grok) can invoke them seamlessly.
4. As a user, I want the agent to read files and inspect directories when answering coding questions, so that I don't have to manually copy and paste code into the prompt.
5. As a user, I want the agent to create and modify files when asked to implement code, so that tasks can be completed autonomously.
6. As a user, I want the agent to run terminal commands (e.g. tests, linters, git status) and inspect their outputs, so that it can verify its own work.
7. As a security-conscious user, I want the agent to ask for my explicit approval (`[y/N]`) before writing to files or running shell commands, so that I maintain complete control over my machine.
8. As a power user, I want an `--auto-approve` / `-y` flag in `icarus run` and `icarus chat`, so that I can permit autonomous execution in trusted environments or scripts.
9. As a user, I want filesystem tools to be jailed to my current working directory by default, so that prompt injections or rogue models cannot inspect or overwrite files outside my project.
10. As a user, I want to see real-time Rich UI panels and spinners when the agent is executing tools, so that I always know what action is taking place.
11. As a user, I want every tool invocation and tool output to be recorded in my SQLite session history, so that I can resume sessions without losing tool context.
12. As a user, I want a hard turn limit (default 25 turns) and per-tool timeout (default 30s), so that the agent cannot get stuck in an expensive infinite loop.
13. As a user, I want pressing Ctrl+C during tool execution to cleanly abort the active tool without crashing the CLI or corrupting the session database.

---

## Implementation Decisions

### Contracts Seam (`packages/contracts`)
- `ToolDefinition`: Pydantic schema for name, description, parameters JSON schema, and safety category (`SAFE_READ` vs `REQUIRES_APPROVAL`).
- `ToolCall`: Encapsulates call ID, function name, and raw JSON arguments.
- `ToolResult`: Encapsulates call ID, output text, exit code / status, and error message if any.
- Extended `MessageRole.TOOL` or `role="tool"` in `PromptMessage` and `MessageModel` for tool result messages.

### Agent Core Seam (`packages/agent-core`)
- **System Prompt Builder** (`icarus_core.agent.prompts`): Generates dynamic system instructions including identity, OS, working directory, and tool usage instructions.
- **Tool Registry** (`icarus_core.tools.registry`): Manages registered tools, validates arguments, checks workspace path boundaries, and handles execution.
- **Approval Engine** (`icarus_core.agent.approvals`): Evaluates tool safety level against configured policy (`INTERACTIVE`, `AUTO_APPROVE`, `DENY`).
- **Autonomous Loop** (`icarus_core.agent.loop`): Orchestrates provider inference, tool call extraction, approval requests, execution, and iterative message feeding.

### CLI UX Seam (`apps/cli`)
- Interactive approval prompt in terminal with styled panel showing tool name, arguments, and warning.
- Live progress spinners and tool result summaries using Rich.
- Global `--auto-approve` / `-y` flag added to `icarus run` and `icarus chat`.

---

## Out of Scope for Phase 2
- Remote multi-tenant server execution (`apps/api`) and background daemon (`apps/worker`) (Phase 4).
- Third-party MCP server discovery and dynamic OAuth integrations (Phase 5).
- Cross-platform desktop sidecar (Phase 7).
- Multi-agent swarms or sub-agent hierarchy.
