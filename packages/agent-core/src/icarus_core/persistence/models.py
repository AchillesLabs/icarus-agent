"""SQLAlchemy 2 declarative ORM models for sessions, messages, and runs."""

import uuid
from datetime import UTC, datetime
from typing import Any

from icarus_contracts.jobs import ScheduledJobDTO, ScheduledJobStatus
from icarus_contracts.session import MessageDTO, MessageRole, RunDTO, RunStatus, SessionDTO
from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _generate_uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _ensure_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


class Base(DeclarativeBase):
    """Declarative base class for all Icarus ORM models."""


class SessionModel(Base):
    """Persistent conversation session."""

    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_generate_uuid)
    owner_id: Mapped[str] = mapped_column(
        String(128), nullable=False, default="default", index=True
    )
    mode: Mapped[str] = mapped_column(String(64), nullable=False, default="chat")
    title: Mapped[str] = mapped_column(String(255), nullable=False, default="New Session")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        onupdate=_utcnow,
    )
    metadata_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    messages: Mapped[list["MessageModel"]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="MessageModel.created_at",
    )
    runs: Mapped[list["AgentRunModel"]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
    )

    def to_dto(self) -> SessionDTO:
        """Convert ORM model to immutable Pydantic SessionDTO."""
        return SessionDTO(
            id=self.id,
            owner_id=self.owner_id,
            mode=self.mode,
            title=self.title,
            created_at=self.created_at,
            updated_at=self.updated_at,
            metadata_version=self.metadata_version,
        )


class MessageModel(Base):
    """Persistent chat message belonging to a session."""

    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_generate_uuid)
    session_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    owner_id: Mapped[str] = mapped_column(
        String(128), nullable=False, default="default", index=True
    )
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    content: Mapped[str | None] = mapped_column(Text, nullable=True, default="")
    token_estimate: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    tool_calls: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)
    tool_call_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )

    session: Mapped["SessionModel"] = relationship(back_populates="messages")

    def to_dto(self) -> MessageDTO:
        """Convert ORM model to immutable Pydantic MessageDTO."""
        return MessageDTO(
            id=self.id,
            session_id=self.session_id,
            owner_id=self.owner_id,
            role=MessageRole(self.role)
            if self.role in MessageRole._value2member_map_
            else self.role,
            content=self.content or "",
            token_estimate=self.token_estimate,
            created_at=self.created_at,
            tool_calls=self.tool_calls,
            tool_call_id=self.tool_call_id,
            name=self.name,
        )


class AgentRunModel(Base):
    """Persistent bounded agent execution run."""

    __tablename__ = "agent_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_generate_uuid)
    owner_id: Mapped[str] = mapped_column(
        String(128), nullable=False, default="default", index=True
    )
    session_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="queued", index=True)

    provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    budget_counters: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    error_category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    session: Mapped["SessionModel | None"] = relationship(back_populates="runs")

    def to_dto(self) -> RunDTO:
        """Convert ORM model to immutable Pydantic RunDTO."""
        return RunDTO(
            id=self.id,
            owner_id=self.owner_id,
            session_id=self.session_id,
            status=RunStatus(self.status)
            if self.status in RunStatus._value2member_map_
            else self.status,
            provider=self.provider,
            model=self.model,
            budget_counters=self.budget_counters,
            error_category=self.error_category,
            idempotency_key=self.idempotency_key,
            created_at=self.created_at,
            started_at=self.started_at,
            completed_at=self.completed_at,
        )


class ScheduledJobModel(Base):
    """Persistent scheduled task or reminder."""

    __tablename__ = "scheduled_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_generate_uuid)
    owner_id: Mapped[str] = mapped_column(
        String(128), nullable=False, default="default", index=True
    )
    job_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    scheduled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending", index=True)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    claimed_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        onupdate=_utcnow,
    )

    def to_dto(self) -> ScheduledJobDTO:
        """Convert ORM model to immutable Pydantic ScheduledJobDTO."""
        return ScheduledJobDTO(
            id=self.id,
            owner_id=self.owner_id,
            job_type=self.job_type,
            scheduled_at=_ensure_utc(self.scheduled_at),  # type: ignore[arg-type]
            status=ScheduledJobStatus(self.status)
            if self.status in ScheduledJobStatus._value2member_map_
            else self.status,
            payload=self.payload,
            claimed_by=self.claimed_by,
            claimed_at=_ensure_utc(self.claimed_at),
            completed_at=_ensure_utc(self.completed_at),
            error_message=self.error_message,
            retry_count=self.retry_count,
            created_at=_ensure_utc(self.created_at),  # type: ignore[arg-type]
            updated_at=_ensure_utc(self.updated_at),  # type: ignore[arg-type]
        )
