# 02: Context Budget Manager and Context Hierarchy Assembly

**What to build:** A dynamic context budgeting and prioritized prompt assembly engine. Computes effective input budgets using `input_budget = model_context_window - output_reserve - safety_margin` with configurable values in `config.toml`. Assembles prompt payloads according to a strict hierarchy (non-negotiable system and safety rules -> user task constraints -> tool schemas -> compaction summary -> recent messages), guaranteeing that core safety instructions are never crowded out by conversational history.

**Blocked by:** 01: Token Counting Engine and Provider-Aware Estimators

**Status:** ready-for-agent

- [ ] Implement `ContextBudgetConfig` in `icarus_contracts` and `ContextBudgetManager` in `icarus_core`.
- [ ] Implement input budget calculation from provider model capabilities, output reserves, and safety margins.
- [ ] Enforce context hierarchy assembly ordering so system prompts and active constraints are prioritized.
- [ ] Add configuration fields to `config.toml` (e.g. `safety_margin_tokens`, `output_reserve_tokens`, `compaction_threshold`).
- [ ] Unit tests verify budget calculation, threshold detection, and prompt assembly ordering across various model context limits.
