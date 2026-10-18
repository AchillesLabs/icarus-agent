# 03: Turn-Boundary History Compactor with Tool Pairing Protection

**What to build:** An intelligent conversation history compactor that partitions messages into older compaction candidates and recent retained turns. Crucially preserves the function-calling contract: assistant messages with `tool_calls` are never separated from their corresponding `tool` results. Generates a structured markdown summary retaining the original user goal, technical decisions, files modified, tool outputs, and unresolved next steps, replacing compacted turns with an explicit summary message.

**Blocked by:** 01: Token Counting Engine and Provider-Aware Estimators, 02: Context Budget Manager and Context Hierarchy Assembly

**Status:** completed

- [x] Implement `HistoryCompactor` in `icarus_core.agent` with turn-boundary partitioning logic.
- [x] Strictly enforce the tool-call pairing invariant: never slice between an assistant message containing `tool_calls` and its matching `tool` results.
- [x] Generate structured markdown summary schema capturing user intent, decisions, touched files, tool results, and open questions.
- [x] Replace compacted messages with a single summary message or anchor preserving conversational continuity.
- [x] Unit tests verify turn-boundary slicing, tool-pair protection, and summary message formatting across diverse message sequences.

