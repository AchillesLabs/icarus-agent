"""Developer logging subsystem with structured rotating file output and secret redaction."""

from __future__ import annotations

import logging
import os
import re
from logging.handlers import RotatingFileHandler
from pathlib import Path

from icarus_core.paths import get_icarus_logs_dir

REDACTED_TOKEN = "[REDACTED]"

# Regex patterns matching known secret tokens and authorization headers
SECRET_PATTERNS: list[re.Pattern[str]] = [
    # xAI API keys
    re.compile(r"\bxai-[A-Za-z0-9_\-]{8,}\b"),
    # Groq API keys
    re.compile(r"\bgsk_[A-Za-z0-9_\-]{20,}\b"),
    # OpenRouter API keys (e.g. sk-or-v1-... or sk-or-...)
    re.compile(r"\bsk-or-v1-[A-Za-z0-9_\-]+\b"),
    re.compile(r"\bsk-or-[A-Za-z0-9_\-]+\b"),
    # Standard OpenAI / generic LLM provider keys
    re.compile(r"\bsk-[A-Za-z0-9_\-]{20,}\b"),
    # HTTP Bearer authentication tokens
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9\-_.~+/]+=*"),
    # Key-value secret assignments in configuration strings or query params
    re.compile(
        r"(?i)\b(api[_-]?key|secret|password|access[_-]?token)\s*[:=]\s*['\"]?([A-Za-z0-9_\-\.]{8,})['\"]?"
    ),
]


def redact_secrets(text: str) -> str:
    """Scan string for known secret patterns and replace them with [REDACTED]."""
    if not text:
        return text

    redacted = text
    for pattern in SECRET_PATTERNS:
        # If the pattern contains group 2 (e.g. api_key=secret), only redact the secret group
        if pattern.groups == 2:
            redacted = pattern.sub(rf"\1={REDACTED_TOKEN}", redacted)
        else:
            redacted = pattern.sub(REDACTED_TOKEN, redacted)

    return redacted


class RedactingFilter(logging.Filter):
    """Logging filter that redacts secrets from LogRecord messages and arguments."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = redact_secrets(record.msg)

        if record.args:
            if isinstance(record.args, dict):
                record.args = {
                    k: redact_secrets(v) if isinstance(v, str) else v
                    for k, v in record.args.items()
                }
            elif isinstance(record.args, tuple):
                record.args = tuple(
                    redact_secrets(a) if isinstance(a, str) else a for a in record.args
                )
            elif isinstance(record.args, list):
                record.args = [redact_secrets(a) if isinstance(a, str) else a for a in record.args]

        if record.exc_text:
            record.exc_text = redact_secrets(record.exc_text)

        return True


class RedactingFormatter(logging.Formatter):
    """Logging formatter that ensures full rendered output is redacted."""

    def format(self, record: logging.LogRecord) -> str:
        formatted = super().format(record)
        return redact_secrets(formatted)


def setup_logging(
    log_dir: Path | None = None,
    log_level: str | None = None,
    max_bytes: int = 10 * 1024 * 1024,
    backup_count: int = 5,
) -> logging.Logger:
    """Configure rotating file logger writing to cli.log with automated secret redaction."""
    effective_dir = log_dir or get_icarus_logs_dir()
    effective_dir.mkdir(parents=True, exist_ok=True)
    log_file = effective_dir / "cli.log"

    env_level = (
        log_level
        or os.environ.get("ICARUS_LOG_LEVEL")
        or os.environ.get("OPENAGENT_LOG_LEVEL")
        or "INFO"
    )
    level = getattr(logging, env_level.upper(), logging.INFO)

    logger = logging.getLogger("icarus")
    logger.setLevel(level)

    # Avoid adding duplicate RotatingFileHandler if setup_logging is called multiple times
    for handler in list(logger.handlers):
        if (
            isinstance(handler, RotatingFileHandler)
            and Path(handler.baseFilename).resolve() == log_file.resolve()
        ):
            handler.setLevel(level)
            return logger

    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    file_handler.setLevel(level)

    formatter = RedactingFormatter(
        "%(asctime)s [%(levelname)s] %(name)s (%(process)d): %(message)s"
    )
    file_handler.setFormatter(formatter)
    file_handler.addFilter(RedactingFilter())

    logger.addHandler(file_handler)
    return logger


def get_logger(name: str = "icarus") -> logging.Logger:
    """Return a logger instance under the icarus namespace."""
    if name == "icarus" or name.startswith("icarus."):
        return logging.getLogger(name)
    return logging.getLogger(f"icarus.{name}")
