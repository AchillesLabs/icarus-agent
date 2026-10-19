# 02: Structured CloudWatch JSON Logging and Request Correlation Formatter

**GitHub Issue:** [#43](https://github.com/AchillesLabs/icarus-agent/issues/43)
**Parent Spec:** [#41](https://github.com/AchillesLabs/icarus-agent/issues/41)

**What to build:** Configurable structured JSON logging formatter emitting standardized log records with request IDs, tenant IDs, timestamps, log levels, and automatic secret redaction directly ingestible by AWS CloudWatch Logs, FluentBit, and container log aggregators.

**Blocked by:**
- None (can start immediately)

**Status:** ready-for-agent

- [ ] Implement CloudWatchJsonFormatter formatting log records as single-line JSON with standard fields (timestamp, level, logger, message, request_id, tenant_id).
- [ ] Integrate automatic secret redaction scrubbing API keys, Bearer tokens, and vault secrets from log messages and metadata.
- [ ] Support ICARUS_LOG_FORMAT=json environment variable to toggle between human-readable console logs and CloudWatch JSON Lines in production.
- [ ] Ensure API request middleware and worker tasks attach request_id and tenant_id to logging contextvars.
- [ ] Integration tests verify JSON format correctness, secret redaction, and log aggregation compatibility.
