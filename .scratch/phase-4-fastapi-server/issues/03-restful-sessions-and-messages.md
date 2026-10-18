# 03: RESTful Session and Message Management Endpoints

**GitHub Issue:** [#28](https://github.com/AchillesLabs/icarus-agent/issues/28)
**Parent Spec:** [#25](https://github.com/AchillesLabs/icarus-agent/issues/25)

**What to build:** Expose complete RESTful API resources for conversational session lifecycle: `GET /v1/sessions` (with pagination and sorting), `POST /v1/sessions` (create session), `GET /v1/sessions/{id}` (inspect session details and aggregated telemetry), `DELETE /v1/sessions/{id}` (cascade deletion), and `GET/POST /v1/sessions/{id}/messages` (retrieve transcript and append messages).

**Blocked by:** [#27](https://github.com/AchillesLabs/icarus-agent/issues/27) (02: Bearer Authentication Middleware and Tenant-Isolated Request Scoping)

**Status:** ready-for-agent

- [ ] Add `SessionResponse`, `SessionListResponse`, and `MessageResponse` Pydantic schemas in `icarus_contracts`.
- [ ] Implement `GET /v1/sessions` with `limit` and `offset` query parameters returning tenant session summaries.
- [ ] Implement `POST /v1/sessions` creating a new conversation thread bound to the authenticated `owner_id`.
- [ ] Implement `GET /v1/sessions/{id}` returning session metadata, message counts, run counts, and token totals.
- [ ] Implement `DELETE /v1/sessions/{id}` cleanly removing the session and its cascade-related messages and runs.
- [ ] Implement `GET /v1/sessions/{id}/messages` returning the chronological transcript with tool calls and token estimates.
- [ ] API integration tests verify full CRUD lifecycle, pagination, and tenant scoping.
