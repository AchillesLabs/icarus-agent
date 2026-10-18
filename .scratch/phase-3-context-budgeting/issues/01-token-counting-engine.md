# 01: Token Counting Engine and Provider-Aware Estimators

**What to build:** An accurate, fast, and provider-aware token counting engine that computes the token cost of raw text, structured conversation messages, tool calls, and tool definitions. Uses `tiktoken` for models utilizing `cl100k_base` and `o200k_base` tokenizers (OpenAI, Grok, OpenRouter) with an offline heuristic fallback (~4 characters per token). This enables the agent to gauge token consumption and pre-flight prompt payloads before dispatching them to LLM APIs.

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [ ] Implement `TokenCounter` interface and implementations (`TiktokenCounter`, `HeuristicTokenCounter`) in `icarus_core`.
- [ ] Support token estimation for raw strings, `PromptMessage` instances (including role overhead and tool calls), and tool schemas.
- [ ] Fall back gracefully to character heuristic estimator if `tiktoken` is unavailable or model is unsupported.
- [ ] Expose token calculation utilities in `icarus_core` for use across the agent loop and persistence layers.
- [ ] Comprehensive unit tests verify accurate and deterministic token counts for text, messages, and tool definitions.
