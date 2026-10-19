"""Domain contracts and schemas for structured security audit logging."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class AuditEventType(StrEnum):
    """Categorical classification of security-relevant lifecycle events."""

    AUTH_SUCCESS = "auth.success"
    AUTH_FAILURE = "auth.failure"
    TOKEN_CREATED = "token.created"
    TOKEN_REVOKED = "token.revoked"
    VAULT_SECRET_STORED = "vault.stored"
    VAULT_SECRET_ACCESSED = "vault.accessed"
    VAULT_SECRET_DELETED = "vault.deleted"
    RATE_LIMIT_EXCEEDED = "rate_limit.exceeded"
    CONCURRENCY_LIMIT_EXCEEDED = "concurrency_limit.exceeded"
    ACCESS_DENIED = "access.denied"


class AuditSeverity(StrEnum):
    """Severity level indicating risk profile of an audited security action."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class AuditEvent(BaseModel):
    """Normalized structured audit record for security forensics and compliance."""

    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="UTC ISO-8601 timestamp of event occurrence",
    )
    event_type: AuditEventType | str = Field(
        ...,
        description="Standardized classification of the security event",
    )
    severity: AuditSeverity = Field(
        default=AuditSeverity.INFO,
        description="Risk severity level",
    )
    actor_id: str | None = Field(
        default=None,
        description="Identified tenant, user, or client identifier, or None if unauthenticated",
    )
    client_ip: str | None = Field(
        default=None,
        description="Originating client IP address",
    )
    user_agent: str | None = Field(
        default=None,
        description="Client User-Agent header string",
    )
    request_id: str | None = Field(
        default=None,
        description="Unique request tracing identifier if available",
    )
    resource: str | None = Field(
        default=None,
        description="Target resource identifier or URI path",
    )
    action: str = Field(
        ...,
        description="Security action performed (e.g. authenticate, store_credential, rate_limit)",
    )
    outcome: str = Field(
        ...,
        description="Outcome of the action (e.g. allow, deny, throttle, success, failure)",
    )
    details: dict[str, Any] = Field(
        default_factory=dict,
        description="Structured, sanitized metadata contextualizing the event",
    )

    def to_json_line(self) -> str:
        """Serialize event to a single-line JSON string without line breaks."""
        return self.model_dump_json()
