# 07: Multi-Model Aggregator Expansion: OpenRouter and LiteLLM Gateway Adapters

**What to build:** Expand provider capability by adding native support for OpenRouter (granting users access to hundreds of foundation models with a single API key) and an optional LiteLLM gateway adapter. Users can configure OpenRouter in `icarus init` or via `icarus config set default_provider openrouter`, set their model preference (e.g. `anthropic/claude-3.5-sonnet`), and immediately chat or run one-shot tasks with full streaming support.

**Blocked by:**
- 04: Hybrid ModelProvider Protocol with Grok and Mock Adapters
- 05: Interactive Chat REPL with Session Persistence

**Status:** closed

- [x] OpenRouter provider adapter implemented under `icarus_core.providers.openrouter`, supporting model routing and streaming token events.
- [x] LiteLLM gateway adapter implemented as an optional provider backend under `icarus_core.providers.litellm`.
- [x] `icarus init` and `icarus config` allow selecting OpenRouter and saving the OpenRouter API key in the OS keyring.
- [x] `icarus doctor` verifies reachability of OpenRouter API and displays configured models.
- [x] Integration tests verify OpenRouter streaming requests and error normalization.
