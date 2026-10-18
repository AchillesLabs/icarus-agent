# 05: Run Telemetry Accumulation and SQLite Budget Persistence

**What to build:** Granular tracking and persistence of execution telemetry for messages and runs. Computes and records `token_estimate` for every persisted message in SQLite. Accumulates comprehensive run budget counters (`prompt_tokens`, `completion_tokens`, `total_tokens`, `model_calls`, `tool_calls`, `compaction_count`, `elapsed_time_seconds`) and persists them into `agent_runs.budget_counters`.

**Blocked by:** 04: Agent Loop Compaction Integration and Token Guardrails

**Status:** ready-for-agent

- [ ] Compute and record `token_estimate` on `MessageModel` upon every message creation via `MessageRepository`.
- [ ] Accumulate prompt, completion, and total tokens from provider responses or local token estimators during `AgentLoop`.
- [ ] Persist complete `budget_counters` payload into `AgentRunModel` upon run completion or failure.
- [ ] Add Alembic migration if needed to index token estimates and budget counter fields.
- [ ] Unit and persistence tests verify that token estimates and budget counters are accurately stored and queryable in SQLite.
