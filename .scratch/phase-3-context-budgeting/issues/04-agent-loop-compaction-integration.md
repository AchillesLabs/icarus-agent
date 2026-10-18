# 04: Agent Loop Compaction Integration and Token Guardrails

**What to build:** Seamless integration of context budgeting and automatic compaction into the autonomous `AgentLoop`. Before each model turn, the loop estimates context token consumption; if tokens exceed the compaction trigger threshold (e.g. 80% of `input_budget`), compaction executes automatically and emits an `on_compaction` observer event. Enforces optional hard token ceilings (`max_total_tokens`) to safely halt runaway loops.

**Blocked by:** 03: Turn-Boundary History Compactor with Tool Pairing Protection

**Status:** ready-for-agent

- [ ] Integrate `ContextBudgetManager` and `HistoryCompactor` into `AgentLoop` in `icarus_core.agent.loop`.
- [ ] Add `on_compaction(event)` hook to `AgentLoopObserver` protocol and implement Rich styling in `RichAgentObserver`.
- [ ] Wire automatic pre-flight compaction trigger prior to model provider dispatch.
- [ ] Enforce configurable `max_total_tokens` ceiling, halting execution cleanly with `finish_reason="max_tokens"` when reached.
- [ ] Integration tests with `MockModelProvider` verify compaction triggers during execution, preserves tool integrity, and successfully completes runs.
