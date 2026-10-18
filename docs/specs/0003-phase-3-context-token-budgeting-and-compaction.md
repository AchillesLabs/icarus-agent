# Spec 0003: Phase 3 - Context Management, Token Budgeting, History Compaction, and SQLite Persistence

- **Status**: Draft / In Progress
- **Target**: Phase 3 of Icarus Agent Architecture Roadmap
- **Estimated Scope**: Token counting, context budgeting, conversation history compaction, run telemetry counters, and local SQLite session inspection

## Problem Statement

In Phases 1 and 2, Icarus established a solid foundation for configuration, OS keyring security, provider adapters, tool registries, human-in-the-loop approvals, and autonomous execution. However, conversation history currently accumulates monotonically across turns. Every new user prompt, tool call, and tool result appends directly to the active prompt context without accounting for context window limits.

Without active context management:
1. Long-running or tool-heavy sessions rapidly exceed model context ceilings (e.g. 8k, 32k, or 128k tokens), causing provider inference calls to fail with unrecoverable `context_length_exceeded` errors.
2. Token consumption and API costs scale quadratically with session length because the entire verbatim history of file dumps, search results, and tool outputs is repeatedly retransmitted on every single turn.
3. Users and operators have zero visibility into token consumption, cost metrics, or session duration because run telemetry is not aggregated or displayed.
4. Naive truncation methods (such as dropping the oldest messages from the list) catastrophically break LLM function-calling contracts: if an assistant message containing `tool_calls` is retained while its preceding context or subsequent matching `tool` result is dropped, providers reject the request with validation errors. Furthermore, naive truncation risks dropping non-negotiable system safety instructions and original task constraints.

Users need an autonomous context management system that monitors token consumption in real time, enforces strict context budgets, cleanly compacts older conversation history into high-fidelity structured summaries, preserves tool-call invariants, and provides clear visibility into token usage and session history.

---

## Solution

Build **Phase 3: Context Management, Token Budgeting, History Compaction, and SQLite Persistence** for Icarus Agent:

1. **Provider-Aware Token Counting**: A modular token counting engine that combines exact tokenizer encoding (e.g. `tiktoken` for OpenAI, Grok, and OpenRouter models) with a universal heuristic fallback (~4 characters per token) to accurately gauge message, prompt, and tool schema token weights.
2. **Dynamic Context Budgeting**: Enforce the context budget formula before each model invocation:
   `input_budget = model_context_window - output_reserve - safety_margin`
   Ensure non-negotiable system instructions, active constraints, and allowed tool schemas are safeguarded before allocating remaining budget to conversation history.
3. **Context Hierarchy and Prompt Assembly**: Standardize the order of prompt assembly:
   - System persona, environment context, and safety instructions (never evicted)
   - Current user task goals and constraints
   - Active tool definitions and schemas
   - Structured summary of compacted older history
   - Recent conversation turns (retained verbatim)
4. **Intelligent Turn-Boundary Compaction**: When conversation history approaches the context budget threshold (e.g. 80% of `input_budget`), trigger an automated compaction cycle:
   - Partition conversation history into an older compaction candidate window and a recent verbatim window.
   - Guarantee tool-call pairing invariants: Never split an assistant `tool_calls` message from its corresponding `tool` results. Compaction occurs strictly across turn boundaries.
   - Summarize older turns into a concise, structured markdown document capturing original task goals, decisions made, files inspected/modified, key tool outputs, and unresolved next steps.
   - Replace compacted turns with the structured summary, resetting context pressure while maintaining semantic continuity.
5. **Run Budget Telemetry and Usage Persistence**:
   - Aggregate comprehensive execution metrics per agent run: prompt tokens, completion tokens, total tokens, model invocations count, tool invocations count, compaction cycles, and elapsed duration.
   - Record token estimates on individual messages and persist structured budget counters into SQLite (`agent_runs.budget_counters`).
6. **CLI Context & History Observability**:
   - Expose run telemetry upon completion of `icarus run` and `icarus chat`.
   - Provide `icarus sessions` command to browse past sessions, message counts, and token totals.
   - Provide `icarus history <session_id>` command to inspect formatted message transcripts and tool calls from previous runs.

---

## User Stories

1. As a user, I want the agent to automatically estimate the token count of my messages and tool outputs, so that I can anticipate context usage and costs.
2. As a user, I want long multi-turn sessions to continue seamlessly without crashing when approaching the model's context window limit, so that I can finish long complex tasks without interruption.
3. As a developer, I want token estimation to use fast exact tokenizers when available and fall back cleanly to character heuristics offline, so that token budgeting works across all supported cloud and local models.
4. As a user, I want the system prompt, environment details, and safety rules to be permanently preserved during compaction, so that the agent never loses its persona or bypasses safety constraints.
5. As a user, I want the original goal of my task to be carried forward into the compaction summary, so that the agent never forgets what we set out to accomplish.
6. As a user, I want the compaction summary to retain specific technical details like files modified, shell commands executed, and key outputs, so that the agent does not repeat work or hallucinate state.
7. As a developer, I want compaction to strictly preserve tool-call and tool-result pairings, so that provider APIs never reject compacted prompts with function call validation errors.
8. As a user, I want to configure context budget parameters (safety margin, output reserve) in `config.toml`, so that I can adjust context limits to suit my budget or specific model context windows.
9. As a user, I want to see a clear notification in the terminal when compaction is triggered, so that I understand why the conversation context is being summarized.
10. As a user, I want `icarus run` to display a rich telemetry table upon completion showing total turns, prompt tokens, completion tokens, total tokens, and elapsed time, so that I have full transparency into execution costs.
11. As a user, I want every persisted message in SQLite to store an estimated token count, so that resumed sessions can calculate context budget immediately without re-tokenizing the entire database.
12. As a user, I want to list all previous sessions using `icarus sessions`, so that I can easily find and reference past conversations by title, ID, date, and message count.
13. As a user, I want to inspect the transcript of any historical session using `icarus history <session_id>`, so that I can review past prompts, tool executions, and model answers.
14. As a user, I want to set a maximum token budget for autonomous runs (`max_total_tokens`), so that runaway loops halt safely if they consume too many tokens before completing.
15. As a user, I want resumed sessions (`icarus chat --resume`) to accurately reconstruct compacted history and token estimates, so that resumed chats continue smoothly within budget.
16. As an operator, I want all token budget counters to be persisted in `agent_runs.budget_counters` in SQLite, so that future multi-user server backends can audit and enforce user quotas reliably.
17. As a developer, I want all context budgeting and compaction routines to be testable with mock providers and deterministic token counts, so that CI validates context management without spending live API credits.

---

## Implementation Decisions

### Shared Contracts
- Define typed schemas for token metrics, context configurations, and compaction results:
  - `TokenUsage`: Encapsulates prompt tokens, completion tokens, and total tokens.
  - `ContextBudgetConfig`: Encapsulates context window size, output reserve tokens, safety margin tokens, and compaction trigger threshold percentage.
  - `CompactionResult`: Encapsulates original message count, compacted message count, generated summary message, and tokens saved.
  - `SessionSummaryDTO`: Represents high-level session metadata including message count, run count, last active timestamp, and total estimated tokens.
- Extend `RunDTO` and `RunCreate` with strongly typed budget counter structures.

### Core Token Estimation and Context Engine
- **Token Counter**: Implement a provider-aware token counter interface:
  - Exact encoding via `tiktoken` for models utilizing `cl100k_base` or `o200k_base` tokenizers.
  - Heuristic fallback estimator based on normalized character-to-token ratios (~4 characters per token plus per-message overhead).
  - Ability to estimate token size for plain text, structured `PromptMessage` objects (including tool calls), and tool definitions.
- **Context Budget Manager**:
  - Calculates dynamic `input_budget` according to model capabilities and configuration.
  - Evaluates whether the active message history and system prompt exceed the compaction trigger threshold.
  - Assembles prompt contexts according to the prioritized context hierarchy (system & safety instructions &rarr; task instructions &rarr; tool schemas &rarr; compaction summary &rarr; recent conversation turns).
- **History Compactor**:
  - Partitions message history into older candidates and recent retained turns.
  - Enforces the turn-boundary invariant: never split an assistant message with `tool_calls` from its subsequent `tool` results.
  - Generates a structured markdown summary preserving task intent, technical decisions, file modifications, tool execution outputs, and pending actions.
  - Formats the compacted context with an explicit system summary marker to provide clean context grounding for the model.

### Autonomous Agent Loop Integration
- Wire the `ContextBudgetManager` and `HistoryCompactor` into the `AgentLoop` reasoning cycle:
  - Before invoking the provider on each turn, estimate total context tokens.
  - If context tokens exceed the configured compaction threshold, execute compaction and notify the observer.
  - Capture provider-reported usage metadata from completion results and streaming chunks; fall back to local token estimations when provider metadata is absent.
  - Accumulate live budget counters across all turns (input tokens, output tokens, total tokens, model calls, tool calls, compaction events, elapsed time).
  - Enforce `max_total_tokens` guardrail if configured, halting the loop cleanly with an appropriate finish reason if the ceiling is reached.

### Persistence Layer Enhancements
- Update message creation repository to compute and store `token_estimate` for every newly persisted message.
- Update agent run repository to persist comprehensive `budget_counters` upon run completion or failure.
- Add repository queries to list sessions with message counts, latest activity timestamps, and aggregated token usage.
- Add repository queries to fetch complete message transcripts with tool calls and token estimates for session inspection.

### CLI UX & Commands
- Add `icarus sessions` command to the CLI:
  - Renders a Rich table listing past sessions with ID, Title, Mode, Message Count, Estimated Tokens, and Last Active Date.
  - Supports `--limit` option to control display count.
- Add `icarus history <session_id>` command to the CLI:
  - Displays the chronological message log of a specified session with formatted roles, tool call summaries, tool results, and token estimates.
- Add context & budget reporting:
  - Display token usage and duration in `icarus run` execution summaries.
  - Add Rich observer event when compaction occurs during interactive chat or autonomous runs.

---

## Testing Decisions

### What Makes a Good Test
- Tests must verify observable external behavior and contract invariants, rather than private implementation details.
- Context tests should verify that prompts exceeding budget limits are compacted into valid message sequences without orphaning tool calls.
- Telemetry tests should verify that budget counters accurately reflect the model calls, tool calls, and token counts across completed runs.
- Persistence tests should verify that session resumption retains compacted summaries and accurate token counters across process restarts.

### Primary Testing Seams
1. **End-to-End Agent Loop Seam (`AgentLoop.run`)**:
   - Primary high-level seam: Configure `AgentLoop` with a `MockModelProvider` having a constrained synthetic context window (e.g. 600 tokens).
   - Feed multi-turn conversations and verify that compaction triggers automatically, preserves tool call integrity, successfully invokes the model with the compacted context, and records accurate budget counters in the returned `AgentLoopResult`.
2. **Context Manager & Compactor Seam**:
   - Unit test seam for `ContextBudgetManager` and `HistoryCompactor` verifying exact budget calculations, turn boundary preservation, tool-call/tool-result pairing preservation, and summary formatting.
3. **Repository and CLI Seam**:
   - Integration test seam verifying `MessageRepository` token estimate persistence, `RunRepository` budget counter persistence, and `icarus sessions` / `icarus history` CLI command rendering against a temporary SQLite database.

### Prior Art in Codebase
- `tests/test_agent_loop.py`: Demonstrates testing the multi-turn ReAct loop via `AgentLoop` and `MockModelProvider`.
- `tests/test_tool_persistence.py`: Demonstrates verifying SQLite message and tool call persistence.
- `tests/test_turn_limits.py`: Demonstrates testing execution guardrails and observer notifications.
- `tests/test_session_resumption.py`: Demonstrates verifying state restoration and history replay across session restarts.

---

## Out of Scope

- Remote PostgreSQL dual-engine migrations and multi-tenant row-level security (Phase 4).
- FastAPI HTTP streaming endpoints and worker scheduler daemon (Phase 4).
- Vector embeddings, semantic memory retrieval, and RAG search (Phase 5).
- Cloud provider billing integration, cost limits in real currency, and credit card charging.
- Third-party MCP server discovery and OAuth client connections (Phase 5).

---

## Further Notes

### Tracer-Bullet Implementation Plan (7 Tickets)
1. **Ticket 1: Token Counting Engine & Provider-Aware Estimators** (`tiktoken` integration with heuristic fallback for messages and tool schemas).
2. **Ticket 2: Context Budget Manager & Hierarchy Assembly** (input budget calculations, context reservations, and prioritized prompt assembly).
3. **Ticket 3: Turn-Boundary History Compaction & Tool Invariants** (partitioning history, turn-boundary slicing, tool-pair protection, and summary generation).
4. **Ticket 4: Agent Loop Compaction Integration & Token Guardrails** (pre-flight budget checks, automatic compaction trigger, token ceilings, and observer hooks).
5. **Ticket 5: Run Telemetry Accumulation & SQLite Budget Persistence** (aggregating counters, storing `token_estimate` and `budget_counters` in SQLite).
6. **Ticket 6: Session Management CLI Commands (`icarus sessions` and `icarus history`)** (rich table listing of past sessions and transcript inspection).
7. **Ticket 7: Resumption Integrity & End-to-End Context Lifecycle Verification** (verifying compaction, budget tracking, and resumption across multi-turn sessions).
