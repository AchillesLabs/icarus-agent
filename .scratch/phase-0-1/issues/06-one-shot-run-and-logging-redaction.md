# 06: One-Shot CLI Execution and Logging Redaction

**What to build:** Build the non-interactive CLI execution path `icarus run "Prompt"` and the developer logging subsystem. `icarus run` streams model output to standard output, respects standard UNIX piping/redirection, and returns POSIX exit codes (0 for success, 1 for provider/config error). Implement structured rotating file logging under `~/.icarus/logs/cli.log` with automated pattern-based redaction preventing API keys, Bearer tokens, and secrets from appearing in logs or error reports.

**Blocked by:** 05: Interactive Chat REPL with Session Persistence

**Status:** closed

- [x] `icarus run "Prompt"` executes one-shot generation and streams tokens to stdout.
- [x] Command supports reading prompts from stdin pipe (e.g. `cat file.txt | icarus run`).
- [x] Proper exit codes returned (0 on success, 1 on error, 130 on SIGINT cancellation).
- [x] Rotating file logger writes to `~/.icarus/logs/cli.log` (configurable via `ICARUS_LOG_DIR` and `ICARUS_LOG_LEVEL`).
- [x] Automated regex redaction filter intercepts and replaces known secret patterns (`xai-...`, `sk-or-...`, `Bearer ...`) with `[REDACTED]`.
- [x] Tests verify stdout piping, exit codes, and automated log redaction.

