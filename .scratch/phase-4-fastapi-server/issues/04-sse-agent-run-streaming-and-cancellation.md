# 04: Server-Sent Events (SSE) Agent Run Streaming and Cancellation

**GitHub Issue:** [#29](https://github.com/AchillesLabs/icarus-agent/issues/29)
**Parent Spec:** [#25](https://github.com/AchillesLabs/icarus-agent/issues/25)

**What to build:** Real-time Server-Sent Events (SSE) streaming endpoint (`POST /v1/sessions/{id}/runs/stream`) that executes the `AgentLoop` in the background and streams live events to clients: turn beginnings, streaming token deltas, tool execution progress, compaction alerts, and terminal completion payloads. Includes `POST /v1/runs/{id}/cancel` to halt active remote runs cleanly mid-flight.

**Blocked by:** [#28](https://github.com/AchillesLabs/icarus-agent/issues/28) (03: RESTful Session and Message Management Endpoints)

**Status:** completed

- [x] Implement `SSEEventPayload` contract with event types (`turn_start`, `token`, `tool_start`, `tool_end`, `compaction`, `run_completed`, `run_cancelled`, `run_failed`).
- [x] Implement `POST /v1/sessions/{id}/runs/stream` streaming execution events via `EventSourceResponse` (or Starlette `StreamingResponse`).
- [x] Connect remote SSE streaming with `AgentLoopObserver` to push token deltas and tool events live as they occur.
- [x] Implement `POST /v1/runs/{id}/cancel` to signal cancellation to the running agent loop task without corrupting state.
- [x] End-to-end tests verify SSE stream protocol event sequence, token delivery, and cancellation termination.
