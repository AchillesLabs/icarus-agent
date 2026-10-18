# 07: Resumption Integrity and End-to-End Context Lifecycle Verification

**What to build:** End-to-end verification of the context lifecycle, specifically proving that resuming a compacted session (`icarus chat --resume` or `-s <id>`) cleanly re-hydrates the compacted summary, continues multi-turn conversation within budget limits, maintains tool-call pairing integrity, and records accurate cumulative budget counters across multiple runs.

**Blocked by:** 06: Session Management CLI Commands (icarus sessions and icarus history)

**Status:** completed

- [x] End-to-end integration test verifying that a session undergoing compaction can be resumed and continue interacting with models and tools.
- [x] Verify that resumed sessions do not repeat previous compacted tool executions or drop safety guidelines.
- [x] Verify that cumulative budget counters across resumed runs correctly aggregate tokens, model calls, and tool calls in SQLite.
- [x] Verify that all 7 tracer-bullet tickets for Spec 0003 pass and that CI quality gates (`pytest`, `ruff check`, `ruff format`) are 100% green.
