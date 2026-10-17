# 06: Autonomous Multi-Turn ReAct Execution Loop with Live UI Streaming

**What to build:** The core autonomous ReAct execution loop in `icarus_core.agent.loop` powering `icarus run` and `icarus chat`. When a model decides to call one or more tools, the agent pauses direct streaming, requests approval if required, dispatches tool execution, shows real-time Rich spinners and status banners in the CLI, captures tool outputs, and feeds them back to the provider in a multi-turn conversation until the model concludes with a final user-facing response.

**Blocked by:**
- 05: Sandboxed Terminal Execution Tool (run_command) with Timeout Controls

**Status:** ready-for-agent

- [ ] `AgentLoop` state engine implemented under `icarus_core.agent.loop` managing the multi-step cycle between LLM reasoning and tool dispatch.
- [ ] Provider adapters extended to accept tool definitions and parse structured tool-call deltas during streaming.
- [ ] Terminal UI displays real-time tool execution status, tool names, arguments, and outcome summaries using Rich console panels and spinners.
- [ ] Verified end-to-end: a user prompt (e.g. "read pyproject.toml and tell me what the version is") triggers `read_file`, receives output, and answers accurately.
- [ ] Comprehensive unit and integration tests using `MockProvider` asserting multi-turn tool calling cycles and terminal outputs.
