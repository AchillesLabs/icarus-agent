"""Structured security audit logging facility with automated zero-leak secret redaction."""

from __future__ import annotations

import logging
import re
import threading
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from icarus_contracts.audit import AuditEvent, AuditEventType, AuditSeverity

logger = logging.getLogger("icarus.audit")

REDACTED_STR = "[REDACTED]"

# Explicit sensitive key substrings that must always be masked if present in details
SENSITIVE_KEY_SUBSTRINGS = (
    "api_key",
    "token",
    "secret",
    "password",
    "authorization",
    "master_key",
    "bearer",
    "prompt",
    "content",
    "messages",
    "credentials",
    "cookie",
    "ciphertext",
)

# Safe keys that should not be redacted even if they contain substrings like "token" or "key"
SAFE_KEYS = {
    "token_id",
    "token_name",
    "token_prefix",
    "prefix",
    "key_hint",
    "provider",
    "limit",
    "remaining",
    "reset_seconds",
    "retry_after",
    "max_concurrent",
    "active_runs",
    "reason",
    "revoked_at",
    "expires_at",
    "deleted",
    "event_type",
}

# Regex patterns detecting secrets in arbitrary string payloads
SECRET_REGEXES: Sequence[re.Pattern[str]] = (
    # Icarus dynamic tokens (sk_icarus_...)
    re.compile(r"\bsk_icarus_[A-Za-z0-9_\-]{20,}\b"),
    # General LLM provider keys (sk-...)
    re.compile(r"\bsk-[A-Za-z0-9_\-]{20,}\b"),
    # HTTP Bearer tokens
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9\-_.~+/]+=*"),
    # Key-value assignments in configuration strings or queries
    re.compile(
        r"(?i)\b(api[_-]?key|secret|password|access[_-]?token)\s*[:=]\s*['\"]?([A-Za-z0-9_\-\.]{8,})['\"]?"
    ),
)


def sanitize_audit_string(text: str) -> str:
    """Scan string for secret patterns and mask them with [REDACTED]."""
    if not text:
        return text
    sanitized = text
    for pattern in SECRET_REGEXES:
        if pattern.groups == 2:
            sanitized = pattern.sub(rf"\1={REDACTED_STR}", sanitized)
        else:
            sanitized = pattern.sub(REDACTED_STR, sanitized)
    return sanitized


def sanitize_audit_value(key: str | None, value: Any) -> Any:
    """Recursively scrub sensitive keys and secret patterns from metadata values."""
    if key is not None and key.lower() not in SAFE_KEYS:
        lowered = key.lower()
        if any(substr in lowered for substr in SENSITIVE_KEY_SUBSTRINGS):
            return REDACTED_STR

    if isinstance(value, str):
        return sanitize_audit_string(value)
    if isinstance(value, dict):
        return {str(k): sanitize_audit_value(str(k), v) for k, v in value.items()}
    if isinstance(value, list):
        return [sanitize_audit_value(None, item) for item in value]
    if isinstance(value, tuple):
        return tuple(sanitize_audit_value(None, item) for item in value)
    return value


def sanitize_audit_event(event: AuditEvent) -> AuditEvent:
    """Produce a zero-leak sanitized copy of an AuditEvent."""
    sanitized_details = {str(k): sanitize_audit_value(str(k), v) for k, v in event.details.items()}
    sanitized_resource = sanitize_audit_string(event.resource) if event.resource else None
    sanitized_action = sanitize_audit_string(event.action)
    sanitized_outcome = sanitize_audit_string(event.outcome)

    return event.model_copy(
        update={
            "resource": sanitized_resource,
            "action": sanitized_action,
            "outcome": sanitized_outcome,
            "details": sanitized_details,
        }
    )


class AuditLogger:
    """Thread-safe append-only structured audit logger emitting JSON Lines records.

    Captures authentication, authorization, vault modifications, token revocations,
    rate limit violations, and cross-tenant attempts while enforcing zero-leak secret redaction.
    """

    def __init__(
        self,
        file_path: Path | str | None = "audit.jsonl",
        enabled: bool = True,
    ) -> None:
        self.enabled = enabled
        self.file_path = Path(file_path) if file_path is not None else None
        self._lock = threading.Lock()
        self._logger = logger

        if self.file_path is not None and self.enabled:
            self.file_path.parent.mkdir(parents=True, exist_ok=True)

    def log_event(self, event: AuditEvent) -> AuditEvent:
        """Sanitize, serialize, and append an AuditEvent to the audit stream."""
        if not self.enabled:
            return event

        sanitized = sanitize_audit_event(event)
        line = sanitized.to_json_line()

        # 1. Thread-safe append to JSON Lines file
        if self.file_path is not None:
            with self._lock, self.file_path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
                f.flush()

        # 2. Emit to logging handler
        fmt = "AUDIT [%s] %s | actor=%s action=%s outcome=%s resource=%s"
        log_args = (
            sanitized.severity.upper(),
            sanitized.event_type,
            sanitized.actor_id,
            sanitized.action,
            sanitized.outcome,
            sanitized.resource,
        )
        if sanitized.severity == AuditSeverity.CRITICAL:
            self._logger.critical(fmt, *log_args)
        elif sanitized.severity == AuditSeverity.ERROR:
            self._logger.error(fmt, *log_args)
        elif sanitized.severity == AuditSeverity.WARNING:
            self._logger.warning(fmt, *log_args)
        else:
            self._logger.info(fmt, *log_args)

        return sanitized

    def log_auth_success(
        self,
        actor_id: str,
        client_ip: str | None = None,
        user_agent: str | None = None,
        resource: str | None = None,
        request_id: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> AuditEvent:
        """Record a successful authentication event."""
        event = AuditEvent(
            event_type=AuditEventType.AUTH_SUCCESS,
            severity=AuditSeverity.INFO,
            actor_id=actor_id,
            client_ip=client_ip,
            user_agent=user_agent,
            resource=resource,
            request_id=request_id,
            action="authenticate",
            outcome="allow",
            details=details or {},
        )
        return self.log_event(event)

    def log_auth_failure(
        self,
        actor_id: str | None = None,
        client_ip: str | None = None,
        user_agent: str | None = None,
        resource: str | None = None,
        request_id: str | None = None,
        reason: str = "invalid_credentials",
        details: dict[str, Any] | None = None,
    ) -> AuditEvent:
        """Record an authentication failure or missing credentials."""
        merged_details = dict(details or {})
        merged_details["reason"] = reason
        event = AuditEvent(
            event_type=AuditEventType.AUTH_FAILURE,
            severity=AuditSeverity.WARNING,
            actor_id=actor_id,
            client_ip=client_ip,
            user_agent=user_agent,
            resource=resource,
            request_id=request_id,
            action="authenticate",
            outcome="deny",
            details=merged_details,
        )
        return self.log_event(event)

    def log_token_created(
        self,
        actor_id: str,
        token_id: str,
        token_name: str,
        prefix: str,
        client_ip: str | None = None,
        user_agent: str | None = None,
        request_id: str | None = None,
    ) -> AuditEvent:
        """Record dynamic API token issuance."""
        event = AuditEvent(
            event_type=AuditEventType.TOKEN_CREATED,
            severity=AuditSeverity.INFO,
            actor_id=actor_id,
            client_ip=client_ip,
            user_agent=user_agent,
            resource=f"token:{token_id}",
            request_id=request_id,
            action="create_token",
            outcome="success",
            details={"token_id": token_id, "token_name": token_name, "prefix": prefix},
        )
        return self.log_event(event)

    def log_token_revoked(
        self,
        actor_id: str,
        token_id: str,
        client_ip: str | None = None,
        user_agent: str | None = None,
        request_id: str | None = None,
    ) -> AuditEvent:
        """Record API token revocation."""
        event = AuditEvent(
            event_type=AuditEventType.TOKEN_REVOKED,
            severity=AuditSeverity.INFO,
            actor_id=actor_id,
            client_ip=client_ip,
            user_agent=user_agent,
            resource=f"token:{token_id}",
            request_id=request_id,
            action="revoke_token",
            outcome="success",
            details={"token_id": token_id},
        )
        return self.log_event(event)

    def log_vault_credential_stored(
        self,
        actor_id: str,
        provider: str,
        key_hint: str,
        client_ip: str | None = None,
        user_agent: str | None = None,
        request_id: str | None = None,
    ) -> AuditEvent:
        """Record registration or update of an encrypted vault BYOK credential."""
        event = AuditEvent(
            event_type=AuditEventType.VAULT_SECRET_STORED,
            severity=AuditSeverity.INFO,
            actor_id=actor_id,
            client_ip=client_ip,
            user_agent=user_agent,
            resource=f"vault:{provider}",
            request_id=request_id,
            action="store_credential",
            outcome="success",
            details={"provider": provider, "key_hint": key_hint},
        )
        return self.log_event(event)

    def log_vault_credential_deleted(
        self,
        actor_id: str,
        provider: str,
        client_ip: str | None = None,
        user_agent: str | None = None,
        request_id: str | None = None,
    ) -> AuditEvent:
        """Record deletion of a vault BYOK credential."""
        event = AuditEvent(
            event_type=AuditEventType.VAULT_SECRET_DELETED,
            severity=AuditSeverity.INFO,
            actor_id=actor_id,
            client_ip=client_ip,
            user_agent=user_agent,
            resource=f"vault:{provider}",
            request_id=request_id,
            action="delete_credential",
            outcome="success",
            details={"provider": provider},
        )
        return self.log_event(event)

    def log_rate_limit_exceeded(
        self,
        actor_id: str | None,
        client_ip: str | None = None,
        user_agent: str | None = None,
        resource: str | None = None,
        limit: int = 0,
        retry_after: int = 0,
        request_id: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> AuditEvent:
        """Record a sliding-window rate limit violation."""
        merged_details = dict(details or {})
        merged_details.update({"limit": limit, "retry_after": retry_after})
        event = AuditEvent(
            event_type=AuditEventType.RATE_LIMIT_EXCEEDED,
            severity=AuditSeverity.WARNING,
            actor_id=actor_id,
            client_ip=client_ip,
            user_agent=user_agent,
            resource=resource,
            request_id=request_id,
            action="rate_limit",
            outcome="throttle",
            details=merged_details,
        )
        return self.log_event(event)

    def log_concurrency_limit_exceeded(
        self,
        actor_id: str,
        client_ip: str | None = None,
        user_agent: str | None = None,
        resource: str | None = None,
        max_concurrent: int = 0,
        active_runs: int = 0,
        request_id: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> AuditEvent:
        """Record an execution concurrency ceiling violation."""
        merged_details = dict(details or {})
        merged_details.update({"max_concurrent": max_concurrent, "active_runs": active_runs})
        event = AuditEvent(
            event_type=AuditEventType.CONCURRENCY_LIMIT_EXCEEDED,
            severity=AuditSeverity.WARNING,
            actor_id=actor_id,
            client_ip=client_ip,
            user_agent=user_agent,
            resource=resource,
            request_id=request_id,
            action="concurrency_limit",
            outcome="throttle",
            details=merged_details,
        )
        return self.log_event(event)

    def log_access_denied(
        self,
        actor_id: str | None,
        client_ip: str | None = None,
        user_agent: str | None = None,
        resource: str | None = None,
        request_id: str | None = None,
        reason: str = "cross_tenant_access_denied",
        details: dict[str, Any] | None = None,
    ) -> AuditEvent:
        """Record an unauthorized cross-tenant resource access attempt."""
        merged_details = dict(details or {})
        merged_details["reason"] = reason
        event = AuditEvent(
            event_type=AuditEventType.ACCESS_DENIED,
            severity=AuditSeverity.CRITICAL,
            actor_id=actor_id,
            client_ip=client_ip,
            user_agent=user_agent,
            resource=resource,
            request_id=request_id,
            action="access_check",
            outcome="deny",
            details=merged_details,
        )
        return self.log_event(event)

    def read_events(self, limit: int | None = None) -> list[AuditEvent]:
        """Read all emitted audit events from the file (useful for auditing and tests)."""
        if self.file_path is None or not self.file_path.exists():
            return []

        events: list[AuditEvent] = []
        with self._lock, self.file_path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    events.append(AuditEvent.model_validate_json(line))

        if limit is not None:
            return events[-limit:]
        return events

    def clear(self) -> None:
        """Clear audit log file contents (primarily for test isolation)."""
        if self.file_path is not None and self.file_path.exists():
            with self._lock:
                self.file_path.write_text("", encoding="utf-8")
