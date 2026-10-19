# 05: Natural Language Background Reminders & Autonomous Scheduler Integration with Desktop Notifications

**GitHub Issue:** [#53](https://github.com/AchillesLabs/icarus-agent/issues/53)
**Parent Spec:** [#41](https://github.com/AchillesLabs/icarus-agent/issues/41)

**What to build:** Conversational scheduling tools enabling the agent to parse natural language time expressions into scheduled job rows in the Phase 4 PostgreSQL/SQLite database, executed by the background worker daemon with cross-platform desktop notifications upon completion.

**Blocked by:** None (can start immediately)

**Status:** closed

## Acceptance criteria

- [x] Implement ScheduleReminderTool and ListRemindersTool in ToolRegistry for conversational scheduling (e.g. 'remind me in 2 hours to check flight prices').
- [x] Parse natural language relative and absolute datetime expressions into UTC timestamps.
- [x] Persist scheduled reminder tasks into Phase 4 jobs database table with payload and target execution time.
- [x] Integrate cross-platform desktop notification emitter in background worker daemon alerting users upon reminder trigger.
- [x] Automated unit and integration tests verify datetime parsing, job row persistence, worker claiming, and notification dispatch.

