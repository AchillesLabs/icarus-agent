# 04: Hybrid ModelProvider Protocol with Grok and Mock Adapters

**What to build:** Build the core LLM abstraction layer in `icarus_core.providers`. Define the `ModelProvider` abstract protocol with methods for generating completions, streaming token deltas, and exposing model capability metadata. Implement a deterministic `MockProvider` for fast, offline CI test execution with zero credit consumption. Implement a direct Grok (xAI) adapter using REST/SDK that streams tokens and normalizes API errors (HTTP 401 invalid key, HTTP 429 rate limit, network timeout) into domain exception types.

**Blocked by:** 01: Monorepo Foundation and Health Doctor Tracer Bullet

**Status:** closed

- [x] `ModelProvider` abstract protocol defined with async `generate`, `stream`, and `get_capabilities` methods.
- [x] Domain exception hierarchy established (`AuthenticationError`, `RateLimitError`, `ContextLengthExceededError`, `ProviderUnavailableError`).
- [x] Deterministic `MockProvider` implemented to simulate token streams, latency, and simulated error conditions for offline testing.
- [x] Grok (`xai`) direct provider adapter implemented, supporting models like `grok-2` and `grok-beta` with live streaming.
- [x] Provider registry maps provider names to their adapter factories and verifies configured credentials.
- [x] Comprehensive test suite validates protocol conformance, token event streaming, and exception normalization.
