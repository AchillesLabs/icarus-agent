"""Tests for structured rotating file logging and automated secret redaction."""

import logging
from pathlib import Path
from unittest.mock import patch

from icarus_core.logging import (
    RedactingFilter,
    RedactingFormatter,
    redact_secrets,
    setup_logging,
)


def test_redact_xai_secret():
    raw = "Connecting to provider with key xai-1234567890abcdef1234567890abcdef"
    redacted = redact_secrets(raw)
    assert "xai-1234567890abcdef" not in redacted
    assert "[REDACTED]" in redacted
    assert redacted == "Connecting to provider with key [REDACTED]"


def test_redact_openrouter_secret():
    raw = "Resolved credential: sk-or-v1-abcdef1234567890abcdef1234567890"
    redacted = redact_secrets(raw)
    assert "sk-or-v1-abcdef" not in redacted
    assert "[REDACTED]" in redacted
    assert redacted == "Resolved credential: [REDACTED]"


def test_redact_bearer_token():
    raw = "Authorization: Bearer secret-bearer-token-123456789"
    redacted = redact_secrets(raw)
    assert "secret-bearer-token" not in redacted
    assert "[REDACTED]" in redacted
    assert redacted == "Authorization: [REDACTED]"


def test_redact_multiple_secrets_in_single_string():
    raw = "Key 1: xai-abc1234567890, Key 2: sk-or-v1-xyz9876543210, Auth: Bearer mytoken"
    redacted = redact_secrets(raw)
    assert "xai-abc1234567890" not in redacted
    assert "sk-or-v1-xyz9876543210" not in redacted
    assert "mytoken" not in redacted
    assert redacted.count("[REDACTED]") == 3


def test_clean_text_unchanged():
    raw = "Model response completed in 0.42 seconds with 150 tokens generated."
    redacted = redact_secrets(raw)
    assert redacted == raw


def test_redacting_filter_modifies_log_record():
    filter_ = RedactingFilter()
    record = logging.LogRecord(
        name="icarus.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=10,
        msg="Using secret key: %s",
        args=("xai-secret-key-12345678",),
        exc_info=None,
    )
    result = filter_.filter(record)
    assert result is True
    # The formatted message from record must be redacted
    formatted = record.getMessage()
    assert "xai-secret-key-12345678" not in formatted
    assert "[REDACTED]" in formatted


def test_redacting_formatter_redacts_entire_message_and_exceptions():
    formatter = RedactingFormatter("%(levelname)s: %(message)s")
    record = logging.LogRecord(
        name="icarus.test",
        level=logging.ERROR,
        pathname=__file__,
        lineno=20,
        msg="Authentication failed with Bearer my-secret-jwt-token",
        args=(),
        exc_info=None,
    )
    output = formatter.format(record)
    assert "my-secret-jwt-token" not in output
    assert "ERROR: Authentication failed with [REDACTED]" in output


def test_setup_logging_creates_cli_log_with_rotation_and_redaction(tmp_path: Path):
    log_dir = tmp_path / "logs"
    with patch.dict("os.environ", {"ICARUS_LOG_DIR": str(log_dir), "ICARUS_LOG_LEVEL": "DEBUG"}):
        logger = setup_logging(log_dir=log_dir, log_level="DEBUG")
        assert logger is not None
        assert logger.level == logging.DEBUG

        log_file = log_dir / "cli.log"
        assert log_file.exists()

        # Log a secret and verify redaction in the physical file
        logger.info("Initialized session with key xai-test-secret-99999999")
        logger.debug("Bearer token in header: Bearer super-secret-token")

        for handler in logger.handlers:
            handler.flush()

        content = log_file.read_text(encoding="utf-8")
        assert "xai-test-secret-99999999" not in content
        assert "super-secret-token" not in content
        assert "[REDACTED]" in content
        assert "Initialized session with key [REDACTED]" in content
