"""Repository interfaces and implementations for session, message, and run entities."""

from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Any

from icarus_contracts import TenantAccessDeniedError
from icarus_contracts.jobs import (
    ScheduledJobCreate,
    ScheduledJobDTO,
    ScheduledJobStatus,
    ScheduledJobUpdate,
)
from icarus_contracts.session import (
    MessageCreate,
    MessageDTO,
    RunCreate,
    RunDTO,
    RunStatus,
    SessionCreate,
    SessionDTO,
    SessionSummaryDTO,
    SessionUpdate,
)
from icarus_contracts.tokens import ApiTokenResponse
from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from icarus_core.persistence.database import DatabaseManager
from icarus_core.persistence.models import (
    AgentRunModel,
    MessageModel,
    ScheduledJobModel,
    SessionModel,
    TenantApiTokenModel,
)
from icarus_core.tokens import TokenCounter, get_token_counter


class SessionRepository:
    """Repository handling CRUD operations and queries for conversation sessions."""

    def __init__(self, db_manager: DatabaseManager | Session) -> None:
        self.db = db_manager

    @contextmanager
    def _session_scope(self) -> Generator[Session, None, None]:
        if hasattr(self.db, "session_scope"):
            with self.db.session_scope() as session:
                yield session
        else:
            yield self.db  # type: ignore[misc]

    def create_session(
        self,
        session_create: SessionCreate,
        owner_id: str | None = None,
    ) -> SessionDTO:
        """Create and persist a new conversation session."""
        effective_owner = owner_id or session_create.owner_id
        session_model = SessionModel(
            owner_id=effective_owner,
            mode=session_create.mode,
            title=session_create.title,
        )
        with self._session_scope() as session:
            session.add(session_model)
            session.flush()
            session.refresh(session_model)
            return session_model.to_dto()

    def get_session(self, session_id: str, owner_id: str = "default") -> SessionDTO | None:
        """Retrieve a session by its ID and owner."""
        with self._session_scope() as session:
            stmt = select(SessionModel).where(
                SessionModel.id == session_id,
                SessionModel.owner_id == owner_id,
            )
            result = session.execute(stmt).scalar_one_or_none()
            return result.to_dto() if result is not None else None

    def list_sessions(
        self,
        owner_id: str = "default",
        limit: int = 50,
        offset: int = 0,
    ) -> list[SessionDTO]:
        """List sessions belonging to an owner ordered by updated_at descending."""
        with self._session_scope() as session:
            stmt = (
                select(SessionModel)
                .where(SessionModel.owner_id == owner_id)
                .order_by(SessionModel.updated_at.desc(), SessionModel.created_at.desc())
                .offset(offset)
                .limit(limit)
            )
            results = session.execute(stmt).scalars().all()
            return [model.to_dto() for model in results]

    def count_sessions(self, owner_id: str = "default") -> int:
        """Count total sessions belonging to an owner."""
        with self._session_scope() as session:
            stmt = select(func.count(SessionModel.id)).where(SessionModel.owner_id == owner_id)
            return int(session.execute(stmt).scalar() or 0)

    def get_latest_session(self, owner_id: str = "default") -> SessionDTO | None:
        """Return the most recently updated or created session for an owner."""
        sessions = self.list_sessions(owner_id=owner_id, limit=1)
        return sessions[0] if sessions else None

    def update_session(
        self,
        session_id: str,
        update: SessionUpdate,
        owner_id: str = "default",
    ) -> SessionDTO | None:
        """Update fields of an existing session."""
        with self._session_scope() as session:
            stmt = select(SessionModel).where(
                SessionModel.id == session_id,
                SessionModel.owner_id == owner_id,
            )
            model = session.execute(stmt).scalar_one_or_none()
            if model is None:
                return None

            if update.title is not None:
                model.title = update.title
            if update.mode is not None:
                model.mode = update.mode
            if update.metadata_version is not None:
                model.metadata_version = update.metadata_version
            model.updated_at = datetime.now(UTC)

            session.flush()
            session.refresh(model)
            return model.to_dto()

    def delete_session(self, session_id: str, owner_id: str = "default") -> bool:
        """Delete a session by ID and owner."""
        with self._session_scope() as session:
            stmt = select(SessionModel).where(
                SessionModel.id == session_id,
                SessionModel.owner_id == owner_id,
            )
            model = session.execute(stmt).scalar_one_or_none()
            if model is None:
                return False
            session.delete(model)
            return True

    def list_session_summaries(
        self,
        owner_id: str = "default",
        limit: int = 50,
        offset: int = 0,
    ) -> list[SessionSummaryDTO]:
        """List session summaries with message counts, run counts, and token totals."""
        with self._session_scope() as session:
            msg_subq = (
                select(
                    MessageModel.session_id,
                    func.count(MessageModel.id).label("message_count"),
                    func.coalesce(func.sum(MessageModel.token_estimate), 0).label("token_total"),
                )
                .where(MessageModel.owner_id == owner_id)
                .group_by(MessageModel.session_id)
                .subquery()
            )

            run_subq = (
                select(
                    AgentRunModel.session_id,
                    func.count(AgentRunModel.id).label("run_count"),
                )
                .where(AgentRunModel.owner_id == owner_id)
                .group_by(AgentRunModel.session_id)
                .subquery()
            )

            stmt = (
                select(
                    SessionModel,
                    func.coalesce(msg_subq.c.message_count, 0).label("message_count"),
                    func.coalesce(msg_subq.c.token_total, 0).label("token_total"),
                    func.coalesce(run_subq.c.run_count, 0).label("run_count"),
                )
                .outerjoin(msg_subq, SessionModel.id == msg_subq.c.session_id)
                .outerjoin(run_subq, SessionModel.id == run_subq.c.session_id)
                .where(SessionModel.owner_id == owner_id)
                .order_by(SessionModel.updated_at.desc(), SessionModel.created_at.desc())
                .offset(offset)
                .limit(limit)
            )

            rows = session.execute(stmt).all()
            summaries = []
            for sess_model, msg_cnt, tok_total, run_cnt in rows:
                summaries.append(
                    SessionSummaryDTO(
                        id=sess_model.id,
                        owner_id=sess_model.owner_id,
                        mode=sess_model.mode,
                        title=sess_model.title,
                        created_at=sess_model.created_at,
                        updated_at=sess_model.updated_at,
                        message_count=int(msg_cnt),
                        run_count=int(run_cnt),
                        total_estimated_tokens=int(tok_total),
                    )
                )
            return summaries

    def get_session_summary(
        self,
        session_id: str,
        owner_id: str = "default",
    ) -> SessionSummaryDTO | None:
        """Retrieve aggregated summary for a specific session."""
        with self._session_scope() as session:
            msg_subq = (
                select(
                    MessageModel.session_id,
                    func.count(MessageModel.id).label("message_count"),
                    func.coalesce(func.sum(MessageModel.token_estimate), 0).label("token_total"),
                )
                .where(MessageModel.session_id == session_id, MessageModel.owner_id == owner_id)
                .group_by(MessageModel.session_id)
                .subquery()
            )

            run_subq = (
                select(
                    AgentRunModel.session_id,
                    func.count(AgentRunModel.id).label("run_count"),
                )
                .where(AgentRunModel.session_id == session_id, AgentRunModel.owner_id == owner_id)
                .group_by(AgentRunModel.session_id)
                .subquery()
            )

            stmt = (
                select(
                    SessionModel,
                    func.coalesce(msg_subq.c.message_count, 0).label("message_count"),
                    func.coalesce(msg_subq.c.token_total, 0).label("token_total"),
                    func.coalesce(run_subq.c.run_count, 0).label("run_count"),
                )
                .outerjoin(msg_subq, SessionModel.id == msg_subq.c.session_id)
                .outerjoin(run_subq, SessionModel.id == run_subq.c.session_id)
                .where(SessionModel.id == session_id, SessionModel.owner_id == owner_id)
            )

            row = session.execute(stmt).first()
            if row is None:
                return None
            sess_model, msg_cnt, tok_total, run_cnt = row
            return SessionSummaryDTO(
                id=sess_model.id,
                owner_id=sess_model.owner_id,
                mode=sess_model.mode,
                title=sess_model.title,
                created_at=sess_model.created_at,
                updated_at=sess_model.updated_at,
                message_count=int(msg_cnt),
                run_count=int(run_cnt),
                total_estimated_tokens=int(tok_total),
            )

    def archive_session(
        self,
        session_id: str,
        owner_id: str = "default",
    ) -> SessionDTO | None:
        """Mark a session as archived by updating its mode."""
        return self.update_session(
            session_id=session_id,
            update=SessionUpdate(mode="archived"),
            owner_id=owner_id,
        )


class MessageRepository:
    """Repository handling message appending and retrieval for conversation threads."""

    def __init__(
        self,
        db_manager: DatabaseManager | Session,
        token_counter: TokenCounter | None = None,
    ) -> None:
        self.db = db_manager
        self._token_counter = token_counter

    @contextmanager
    def _session_scope(self) -> Generator[Session, None, None]:
        if hasattr(self.db, "session_scope"):
            with self.db.session_scope() as session:
                yield session
        else:
            yield self.db  # type: ignore[misc]

    @property
    def token_counter(self) -> TokenCounter:
        if self._token_counter is None:
            self._token_counter = get_token_counter()
        return self._token_counter

    def create_message(
        self,
        message_create: MessageCreate,
        owner_id: str | None = None,
    ) -> MessageDTO:
        """Append a message to a session thread and bump session updated_at."""
        effective_owner = owner_id or message_create.owner_id
        role_value = (
            message_create.role.value
            if hasattr(message_create.role, "value")
            else str(message_create.role)
        )
        serialized_tool_calls: list[dict[str, Any]] | None = None
        if message_create.tool_calls:
            serialized_tool_calls = [
                tc.model_dump() if hasattr(tc, "model_dump") else dict(tc)
                for tc in message_create.tool_calls
            ]

        token_estimate = message_create.token_estimate
        if token_estimate is None:
            token_estimate = self.token_counter.count_message(message_create)

        msg_model = MessageModel(
            session_id=message_create.session_id,
            owner_id=effective_owner,
            role=role_value,
            content=message_create.content or "",
            token_estimate=token_estimate,
            tool_calls=serialized_tool_calls,
            tool_call_id=message_create.tool_call_id,
            name=message_create.name,
        )
        with self._session_scope() as session:
            # Check session exists for owner and touch updated_at
            session_stmt = select(SessionModel).where(
                SessionModel.id == message_create.session_id,
                SessionModel.owner_id == effective_owner,
            )
            parent_session = session.execute(session_stmt).scalar_one_or_none()
            if parent_session is not None:
                parent_session.updated_at = datetime.now(UTC)

            session.add(msg_model)
            session.flush()
            session.refresh(msg_model)
            return msg_model.to_dto()

    def list_messages(
        self,
        session_id: str,
        owner_id: str = "default",
    ) -> list[MessageDTO]:
        """List all messages in a session in chronological order."""
        with self._session_scope() as session:
            stmt = (
                select(MessageModel)
                .where(
                    MessageModel.session_id == session_id,
                    MessageModel.owner_id == owner_id,
                )
                .order_by(MessageModel.created_at.asc())
            )
            results = session.execute(stmt).scalars().all()
            return [model.to_dto() for model in results]

    def get_message(self, message_id: str, owner_id: str = "default") -> MessageDTO | None:
        """Retrieve a specific message by its ID and owner."""
        with self._session_scope() as session:
            stmt = select(MessageModel).where(
                MessageModel.id == message_id,
                MessageModel.owner_id == owner_id,
            )
            result = session.execute(stmt).scalar_one_or_none()
            return result.to_dto() if result is not None else None

    def delete_messages_for_session(
        self,
        session_id: str,
        owner_id: str = "default",
    ) -> int:
        """Delete all messages belonging to a given session."""
        with self._session_scope() as session:
            stmt = delete(MessageModel).where(
                MessageModel.session_id == session_id,
                MessageModel.owner_id == owner_id,
            )
            result = session.execute(stmt)
            return result.rowcount  # type: ignore[return-value]

    def get_session_token_total(
        self,
        session_id: str,
        owner_id: str = "default",
    ) -> int:
        """Calculate total estimated tokens across all messages in a session."""
        with self._session_scope() as session:
            stmt = select(func.coalesce(func.sum(MessageModel.token_estimate), 0)).where(
                MessageModel.session_id == session_id,
                MessageModel.owner_id == owner_id,
            )
            return int(session.execute(stmt).scalar() or 0)


class AgentRunRepository:
    """Repository handling execution run registration and state updates."""

    def __init__(self, db_manager: DatabaseManager | Session) -> None:
        self.db = db_manager

    @contextmanager
    def _session_scope(self) -> Generator[Session, None, None]:
        if hasattr(self.db, "session_scope"):
            with self.db.session_scope() as session:
                yield session
        else:
            yield self.db  # type: ignore[misc]

    def create_run(
        self,
        run_create: RunCreate,
        owner_id: str | None = None,
    ) -> RunDTO:
        """Record a new agent run."""
        effective_owner = owner_id or run_create.owner_id
        status_value = (
            run_create.status.value
            if hasattr(run_create.status, "value")
            else str(run_create.status)
        )
        run_model = AgentRunModel(
            owner_id=effective_owner,
            session_id=run_create.session_id,
            status=status_value,
            provider=run_create.provider,
            model=run_create.model,
            budget_counters=run_create.budget_counters,
            idempotency_key=run_create.idempotency_key,
        )
        with self._session_scope() as session:
            session.add(run_model)
            session.flush()
            session.refresh(run_model)
            return run_model.to_dto()

    def get_run(self, run_id: str, owner_id: str = "default") -> RunDTO | None:
        """Retrieve an agent run by ID and owner."""
        with self._session_scope() as session:
            stmt = select(AgentRunModel).where(
                AgentRunModel.id == run_id,
                AgentRunModel.owner_id == owner_id,
            )
            result = session.execute(stmt).scalar_one_or_none()
            return result.to_dto() if result is not None else None

    def update_run(
        self,
        run_id: str,
        status: RunStatus | str | None = None,
        error_category: str | None = None,
        budget_counters: dict | None = None,
        completed: bool = False,
        owner_id: str = "default",
    ) -> RunDTO | None:
        """Update the state, error category, or metrics of an agent run."""
        with self._session_scope() as session:
            stmt = select(AgentRunModel).where(
                AgentRunModel.id == run_id,
                AgentRunModel.owner_id == owner_id,
            )
            model = session.execute(stmt).scalar_one_or_none()
            if model is None:
                return None

            now = datetime.now(UTC)
            if status is not None:
                status_str = status.value if hasattr(status, "value") else str(status)
                model.status = status_str
                if status_str == "running" and model.started_at is None:
                    model.started_at = now

            if error_category is not None:
                model.error_category = error_category
            if budget_counters is not None:
                model.budget_counters = budget_counters
            if completed:
                model.completed_at = now

            session.flush()
            session.refresh(model)
            return model.to_dto()

    def list_runs_for_session(
        self,
        session_id: str,
        owner_id: str = "default",
    ) -> list[RunDTO]:
        """List all runs linked to a specific session."""
        with self._session_scope() as session:
            stmt = (
                select(AgentRunModel)
                .where(
                    AgentRunModel.session_id == session_id,
                    AgentRunModel.owner_id == owner_id,
                )
                .order_by(AgentRunModel.created_at.asc())
            )
            results = session.execute(stmt).scalars().all()
            return [model.to_dto() for model in results]

    def list_runs(
        self,
        session_id: str | None = None,
        owner_id: str = "default",
        limit: int = 50,
        offset: int = 0,
    ) -> list[RunDTO]:
        """List agent runs optionally filtered by session_id, ordered by creation."""
        with self._session_scope() as session:
            stmt = select(AgentRunModel).where(AgentRunModel.owner_id == owner_id)
            if session_id is not None:
                stmt = stmt.where(AgentRunModel.session_id == session_id)
            stmt = stmt.order_by(AgentRunModel.created_at.desc()).offset(offset).limit(limit)
            results = session.execute(stmt).scalars().all()
            return [model.to_dto() for model in results]

    def get_session_budget_totals(
        self,
        session_id: str,
        owner_id: str = "default",
    ) -> dict[str, Any]:
        """Aggregate cumulative budget counters across all runs for a session."""
        runs = self.list_runs_for_session(session_id, owner_id=owner_id)
        totals: dict[str, Any] = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "model_calls": 0,
            "tool_calls": 0,
            "compaction_count": 0,
            "elapsed_time_seconds": 0.0,
            "run_count": len(runs),
        }
        for r in runs:
            if r.budget_counters:
                totals["prompt_tokens"] += r.budget_counters.get("prompt_tokens", 0)
                totals["completion_tokens"] += r.budget_counters.get("completion_tokens", 0)
                totals["total_tokens"] += r.budget_counters.get("total_tokens", 0)
                totals["model_calls"] += r.budget_counters.get("model_calls", 0)
                totals["tool_calls"] += r.budget_counters.get("tool_calls", 0)
                totals["compaction_count"] += r.budget_counters.get("compaction_count", 0)
                totals["elapsed_time_seconds"] = round(
                    totals["elapsed_time_seconds"]
                    + float(r.budget_counters.get("elapsed_time_seconds", 0.0)),
                    4,
                )
        return totals


class TenantSessionRepository(SessionRepository):
    """Tenant-scoped repository for session operations strictly enforcing owner isolation."""

    def __init__(self, db_manager: DatabaseManager | Session, owner_id: str) -> None:
        super().__init__(db_manager)
        if not owner_id or not isinstance(owner_id, str):
            raise ValueError("owner_id must be a non-empty string")
        self.owner_id = owner_id

    def create_session(
        self,
        session_create: SessionCreate,
        owner_id: str | None = None,
    ) -> SessionDTO:
        # Strictly enforce self.owner_id, ignoring any external override attempt
        return super().create_session(session_create, owner_id=self.owner_id)

    def get_session(self, session_id: str, owner_id: str | None = None) -> SessionDTO | None:
        return super().get_session(session_id, owner_id=self.owner_id)

    def list_sessions(
        self,
        owner_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[SessionDTO]:
        return super().list_sessions(owner_id=self.owner_id, limit=limit, offset=offset)

    def count_sessions(self, owner_id: str | None = None) -> int:
        return super().count_sessions(owner_id=self.owner_id)

    def get_latest_session(self, owner_id: str | None = None) -> SessionDTO | None:

        return super().get_latest_session(owner_id=self.owner_id)

    def update_session(
        self,
        session_id: str,
        update: SessionUpdate,
        owner_id: str | None = None,
    ) -> SessionDTO | None:
        return super().update_session(session_id, update, owner_id=self.owner_id)

    def delete_session(self, session_id: str, owner_id: str | None = None) -> bool:
        return super().delete_session(session_id, owner_id=self.owner_id)

    def list_session_summaries(
        self,
        owner_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[SessionSummaryDTO]:
        return super().list_session_summaries(owner_id=self.owner_id, limit=limit, offset=offset)

    def get_session_summary(
        self,
        session_id: str,
        owner_id: str | None = None,
    ) -> SessionSummaryDTO | None:
        return super().get_session_summary(session_id, owner_id=self.owner_id)

    def archive_session(self, session_id: str, owner_id: str | None = None) -> SessionDTO | None:
        return super().archive_session(session_id, owner_id=self.owner_id)


class TenantMessageRepository(MessageRepository):
    """Tenant-scoped repository for message operations strictly enforcing owner isolation."""

    def __init__(
        self,
        db_manager: DatabaseManager | Session,
        owner_id: str,
        token_counter: TokenCounter | None = None,
    ) -> None:
        super().__init__(db_manager, token_counter=token_counter)
        if not owner_id or not isinstance(owner_id, str):
            raise ValueError("owner_id must be a non-empty string")
        self.owner_id = owner_id

    def create_message(
        self,
        message_create: MessageCreate,
        owner_id: str | None = None,
    ) -> MessageDTO:
        # Verify that the target session exists and belongs to self.owner_id
        with self._session_scope() as session:
            stmt = select(SessionModel).where(
                SessionModel.id == message_create.session_id,
            )
            sess = session.execute(stmt).scalar_one_or_none()
            if sess is None:
                raise TenantAccessDeniedError(f"Session '{message_create.session_id}' not found")
            if sess.owner_id != self.owner_id:
                raise TenantAccessDeniedError(
                    f"Cross-tenant access forbidden: session '{message_create.session_id}' "
                    f"belongs to another tenant"
                )

        return super().create_message(message_create, owner_id=self.owner_id)

    def get_message(self, message_id: str, owner_id: str | None = None) -> MessageDTO | None:
        return super().get_message(message_id, owner_id=self.owner_id)

    def list_messages(
        self,
        session_id: str,
        owner_id: str | None = None,
    ) -> list[MessageDTO]:
        return super().list_messages(session_id, owner_id=self.owner_id)

    def delete_messages_for_session(
        self,
        session_id: str,
        owner_id: str | None = None,
    ) -> int:
        return super().delete_messages_for_session(session_id, owner_id=self.owner_id)

    def get_session_token_total(
        self,
        session_id: str,
        owner_id: str | None = None,
    ) -> int:
        return super().get_session_token_total(session_id, owner_id=self.owner_id)


class TenantRunRepository(AgentRunRepository):
    """Tenant-scoped repository for agent run operations strictly enforcing owner isolation."""

    def __init__(self, db_manager: DatabaseManager | Session, owner_id: str) -> None:
        super().__init__(db_manager)
        if not owner_id or not isinstance(owner_id, str):
            raise ValueError("owner_id must be a non-empty string")
        self.owner_id = owner_id

    def create_run(
        self,
        run_create: RunCreate,
        owner_id: str | None = None,
    ) -> RunDTO:
        if run_create.session_id:
            with self._session_scope() as session:
                stmt = select(SessionModel).where(
                    SessionModel.id == run_create.session_id,
                )
                sess = session.execute(stmt).scalar_one_or_none()
                if sess is None:
                    raise TenantAccessDeniedError(f"Session '{run_create.session_id}' not found")
                if sess.owner_id != self.owner_id:
                    raise TenantAccessDeniedError(
                        f"Cross-tenant access forbidden: session '{run_create.session_id}' "
                        f"belongs to another tenant"
                    )

        return super().create_run(run_create, owner_id=self.owner_id)

    def get_run(self, run_id: str, owner_id: str | None = None) -> RunDTO | None:
        return super().get_run(run_id, owner_id=self.owner_id)

    def update_run(
        self,
        run_id: str,
        status: RunStatus | str | None = None,
        error_category: str | None = None,
        budget_counters: dict | None = None,
        completed: bool = False,
        owner_id: str | None = None,
    ) -> RunDTO | None:
        return super().update_run(
            run_id,
            status=status,
            error_category=error_category,
            budget_counters=budget_counters,
            completed=completed,
            owner_id=self.owner_id,
        )

    def list_runs(
        self,
        session_id: str | None = None,
        owner_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[RunDTO]:
        return super().list_runs(
            session_id=session_id, owner_id=self.owner_id, limit=limit, offset=offset
        )

    def list_runs_for_session(
        self,
        session_id: str,
        owner_id: str | None = None,
    ) -> list[RunDTO]:
        return super().list_runs_for_session(session_id, owner_id=self.owner_id)

    def get_session_budget_totals(
        self,
        session_id: str,
        owner_id: str | None = None,
    ) -> dict[str, Any]:
        return super().get_session_budget_totals(session_id, owner_id=self.owner_id)


class ScheduledJobRepository:
    """Repository handling scheduled job registration, queries, and lease claims."""

    def __init__(self, db_manager: DatabaseManager | Session) -> None:
        self.db = db_manager

    @contextmanager
    def _session_scope(self) -> Generator[Session, None, None]:
        if hasattr(self.db, "session_scope"):
            with self.db.session_scope() as session:
                yield session
        else:
            yield self.db  # type: ignore[misc]

    def create_job(
        self,
        job_create: ScheduledJobCreate,
        owner_id: str | None = None,
    ) -> ScheduledJobDTO:
        """Register and persist a new scheduled job or reminder."""
        effective_owner = owner_id or job_create.owner_id or "default"
        job_model = ScheduledJobModel(
            owner_id=effective_owner,
            job_type=job_create.job_type,
            scheduled_at=job_create.scheduled_at,
            payload=job_create.payload,
        )
        with self._session_scope() as session:
            session.add(job_model)
            session.flush()
            session.refresh(job_model)
            return job_model.to_dto()

    def get_job(self, job_id: str, owner_id: str = "default") -> ScheduledJobDTO | None:
        """Retrieve a scheduled job by its ID and owner."""
        with self._session_scope() as session:
            stmt = select(ScheduledJobModel).where(
                ScheduledJobModel.id == job_id,
                ScheduledJobModel.owner_id == owner_id,
            )
            result = session.execute(stmt).scalar_one_or_none()
            return result.to_dto() if result is not None else None

    def list_jobs(
        self,
        owner_id: str = "default",
        status: ScheduledJobStatus | str | None = None,
        job_type: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ScheduledJobDTO]:
        """List scheduled jobs ordered by scheduled_at ascending."""
        with self._session_scope() as session:
            stmt = select(ScheduledJobModel).where(ScheduledJobModel.owner_id == owner_id)
            if status is not None:
                status_str = status.value if hasattr(status, "value") else str(status)
                stmt = stmt.where(ScheduledJobModel.status == status_str)
            if job_type is not None:
                stmt = stmt.where(ScheduledJobModel.job_type == job_type)

            stmt = (
                stmt.order_by(
                    ScheduledJobModel.scheduled_at.asc(),
                    ScheduledJobModel.created_at.asc(),
                )
                .offset(offset)
                .limit(limit)
            )
            results = session.execute(stmt).scalars().all()
            return [model.to_dto() for model in results]

    def update_job(
        self,
        job_id: str,
        update: ScheduledJobUpdate | None = None,
        *,
        status: ScheduledJobStatus | str | None = None,
        error_message: str | None = None,
        retry_count: int | None = None,
        payload: dict[str, Any] | None = None,
        scheduled_at: datetime | None = None,
        completed: bool = False,
        owner_id: str = "default",
    ) -> ScheduledJobDTO | None:
        """Update mutable fields on an existing scheduled job."""
        with self._session_scope() as session:
            stmt = select(ScheduledJobModel).where(
                ScheduledJobModel.id == job_id,
                ScheduledJobModel.owner_id == owner_id,
            )
            model = session.execute(stmt).scalar_one_or_none()
            if model is None:
                return None

            now = datetime.now(UTC)
            if update is not None:
                if update.status is not None:
                    status = update.status
                if update.error_message is not None:
                    error_message = update.error_message
                if update.retry_count is not None:
                    retry_count = update.retry_count
                if update.payload is not None:
                    payload = update.payload
                if update.scheduled_at is not None:
                    scheduled_at = update.scheduled_at
                if update.claimed_by is not None:
                    model.claimed_by = update.claimed_by
                if update.claimed_at is not None:
                    model.claimed_at = update.claimed_at
                if update.completed_at is not None:
                    model.completed_at = update.completed_at

            if status is not None:
                status_str = status.value if hasattr(status, "value") else str(status)
                model.status = status_str
                if status_str == ScheduledJobStatus.COMPLETED.value:
                    model.completed_at = now

            if completed:
                model.status = ScheduledJobStatus.COMPLETED.value
                model.completed_at = now

            if error_message is not None:
                model.error_message = error_message
            if retry_count is not None:
                model.retry_count = retry_count
            if payload is not None:
                model.payload = payload
            if scheduled_at is not None:
                model.scheduled_at = scheduled_at

            model.updated_at = now
            session.flush()
            session.refresh(model)
            return model.to_dto()

    def claim_next_job(
        self,
        worker_id: str,
        job_type: str | None = None,
        lease_duration_seconds: int = 300,
        owner_id: str | None = None,
        now: datetime | None = None,
    ) -> ScheduledJobDTO | None:
        """Atomically claim the next eligible pending or lease-expired scheduled job."""
        current_time = now or datetime.now(UTC)
        lease_threshold = current_time - timedelta(seconds=lease_duration_seconds)

        with self._session_scope() as session:
            stmt = select(ScheduledJobModel).where(
                or_(
                    (ScheduledJobModel.status == ScheduledJobStatus.PENDING.value)
                    & (ScheduledJobModel.scheduled_at <= current_time),
                    (ScheduledJobModel.status == ScheduledJobStatus.CLAIMED.value)
                    & (ScheduledJobModel.claimed_at <= lease_threshold),
                )
            )
            if job_type is not None:
                stmt = stmt.where(ScheduledJobModel.job_type == job_type)
            if owner_id is not None:
                stmt = stmt.where(ScheduledJobModel.owner_id == owner_id)

            stmt = stmt.order_by(
                ScheduledJobModel.scheduled_at.asc(),
                ScheduledJobModel.created_at.asc(),
            ).limit(1)

            bind = session.get_bind()
            if bind is not None and getattr(bind.dialect, "name", None) == "postgresql":
                stmt = stmt.with_for_update(skip_locked=True)

            candidate = session.execute(stmt).scalar_one_or_none()
            if candidate is None:
                return None

            candidate.status = ScheduledJobStatus.CLAIMED.value
            candidate.claimed_by = worker_id
            candidate.claimed_at = current_time
            candidate.updated_at = current_time

            session.flush()
            session.refresh(candidate)
            return candidate.to_dto()

    def complete_job(
        self,
        job_id: str,
        owner_id: str = "default",
    ) -> ScheduledJobDTO | None:
        """Mark a claimed job as successfully completed."""
        return self.update_job(
            job_id=job_id,
            status=ScheduledJobStatus.COMPLETED,
            completed=True,
            owner_id=owner_id,
        )

    def fail_job(
        self,
        job_id: str,
        error_message: str,
        retry: bool = False,
        retry_delay_seconds: int = 60,
        owner_id: str = "default",
    ) -> ScheduledJobDTO | None:
        """Mark a job as failed, or reschedule it for retry with backoff."""
        with self._session_scope() as session:
            stmt = select(ScheduledJobModel).where(
                ScheduledJobModel.id == job_id,
                ScheduledJobModel.owner_id == owner_id,
            )
            model = session.execute(stmt).scalar_one_or_none()
            if model is None:
                return None

            now = datetime.now(UTC)
            model.error_message = error_message
            model.updated_at = now

            if retry:
                model.status = ScheduledJobStatus.PENDING.value
                model.retry_count += 1
                model.scheduled_at = now + timedelta(seconds=retry_delay_seconds)
                model.claimed_by = None
                model.claimed_at = None
            else:
                model.status = ScheduledJobStatus.FAILED.value
                model.completed_at = now

            session.flush()
            session.refresh(model)
            return model.to_dto()

    def delete_job(self, job_id: str, owner_id: str = "default") -> bool:
        """Delete a scheduled job by ID and owner."""
        with self._session_scope() as session:
            stmt = select(ScheduledJobModel).where(
                ScheduledJobModel.id == job_id,
                ScheduledJobModel.owner_id == owner_id,
            )
            model = session.execute(stmt).scalar_one_or_none()
            if model is None:
                return False
            session.delete(model)
            return True


class TenantScheduledJobRepository(ScheduledJobRepository):
    """Tenant-scoped repository for scheduled jobs strictly enforcing owner isolation."""

    def __init__(self, db_manager: DatabaseManager | Session, owner_id: str) -> None:
        super().__init__(db_manager)
        if not owner_id or not isinstance(owner_id, str):
            raise ValueError("owner_id must be a non-empty string")
        self.owner_id = owner_id

    def create_job(
        self,
        job_create: ScheduledJobCreate,
        owner_id: str | None = None,
    ) -> ScheduledJobDTO:
        return super().create_job(job_create, owner_id=self.owner_id)

    def get_job(self, job_id: str, owner_id: str | None = None) -> ScheduledJobDTO | None:
        return super().get_job(job_id, owner_id=self.owner_id)

    def list_jobs(
        self,
        owner_id: str | None = None,
        status: ScheduledJobStatus | str | None = None,
        job_type: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ScheduledJobDTO]:
        return super().list_jobs(
            owner_id=self.owner_id,
            status=status,
            job_type=job_type,
            limit=limit,
            offset=offset,
        )

    def update_job(
        self,
        job_id: str,
        update: ScheduledJobUpdate | None = None,
        *,
        status: ScheduledJobStatus | str | None = None,
        error_message: str | None = None,
        retry_count: int | None = None,
        payload: dict[str, Any] | None = None,
        scheduled_at: datetime | None = None,
        completed: bool = False,
        owner_id: str | None = None,
    ) -> ScheduledJobDTO | None:
        return super().update_job(
            job_id,
            update,
            status=status,
            error_message=error_message,
            retry_count=retry_count,
            payload=payload,
            scheduled_at=scheduled_at,
            completed=completed,
            owner_id=self.owner_id,
        )

    def claim_next_job(
        self,
        worker_id: str,
        job_type: str | None = None,
        lease_duration_seconds: int = 300,
        owner_id: str | None = None,
        now: datetime | None = None,
    ) -> ScheduledJobDTO | None:
        return super().claim_next_job(
            worker_id=worker_id,
            job_type=job_type,
            lease_duration_seconds=lease_duration_seconds,
            owner_id=self.owner_id,
            now=now,
        )

    def complete_job(
        self,
        job_id: str,
        owner_id: str | None = None,
    ) -> ScheduledJobDTO | None:
        return super().complete_job(job_id=job_id, owner_id=self.owner_id)

    def fail_job(
        self,
        job_id: str,
        error_message: str,
        retry: bool = False,
        retry_delay_seconds: int = 60,
        owner_id: str | None = None,
    ) -> ScheduledJobDTO | None:
        return super().fail_job(
            job_id=job_id,
            error_message=error_message,
            retry=retry,
            retry_delay_seconds=retry_delay_seconds,
            owner_id=self.owner_id,
        )

    def delete_job(self, job_id: str, owner_id: str | None = None) -> bool:
        return super().delete_job(job_id=job_id, owner_id=self.owner_id)


class ApiTokenRepository:
    """Repository handling CRUD operations and queries for dynamic API tokens."""

    def __init__(self, db_manager: DatabaseManager | Session) -> None:
        self.db = db_manager

    @contextmanager
    def _session_scope(self) -> Generator[Session, None, None]:
        if hasattr(self.db, "session_scope"):
            with self.db.session_scope() as session:
                yield session
        else:
            yield self.db  # type: ignore[misc]

    def create_token(
        self,
        owner_id: str,
        name: str,
        token_hash: str,
        prefix: str,
        expires_at: datetime | None = None,
    ) -> ApiTokenResponse:
        """Create and persist a new dynamic API access token."""
        token_model = TenantApiTokenModel(
            owner_id=owner_id,
            name=name,
            token_hash=token_hash,
            prefix=prefix,
            expires_at=expires_at,
        )
        with self._session_scope() as session:
            session.add(token_model)
            session.flush()
            session.refresh(token_model)
            return token_model.to_dto()

    def get_token_by_id(
        self,
        token_id: str,
        owner_id: str | None = None,
    ) -> ApiTokenResponse | None:
        """Retrieve an API token by its ID, optionally enforcing owner."""
        with self._session_scope() as session:
            stmt = select(TenantApiTokenModel).where(TenantApiTokenModel.id == token_id)
            if owner_id is not None:
                stmt = stmt.where(TenantApiTokenModel.owner_id == owner_id)
            model = session.execute(stmt).scalar_one_or_none()
            return model.to_dto() if model is not None else None

    def get_token_by_hash(self, token_hash: str) -> ApiTokenResponse | None:
        """Retrieve an API token by its SHA-256 hash."""
        with self._session_scope() as session:
            stmt = select(TenantApiTokenModel).where(TenantApiTokenModel.token_hash == token_hash)
            model = session.execute(stmt).scalar_one_or_none()
            return model.to_dto() if model is not None else None

    def list_tokens(
        self,
        owner_id: str,
        include_revoked: bool = True,
    ) -> list[ApiTokenResponse]:
        """List tokens belonging to an owner ordered by creation date descending."""
        with self._session_scope() as session:
            stmt = select(TenantApiTokenModel).where(TenantApiTokenModel.owner_id == owner_id)
            if not include_revoked:
                stmt = stmt.where(TenantApiTokenModel.revoked_at.is_(None))
            stmt = stmt.order_by(TenantApiTokenModel.created_at.desc())
            models = session.execute(stmt).scalars().all()
            return [model.to_dto() for model in models]

    def revoke_token(
        self,
        token_id: str,
        owner_id: str | None = None,
        revoked_at: datetime | None = None,
    ) -> ApiTokenResponse | None:
        """Mark a token as revoked immediately."""
        with self._session_scope() as session:
            stmt = select(TenantApiTokenModel).where(TenantApiTokenModel.id == token_id)
            if owner_id is not None:
                stmt = stmt.where(TenantApiTokenModel.owner_id == owner_id)
            model = session.execute(stmt).scalar_one_or_none()
            if model is None:
                return None
            if model.revoked_at is None:
                model.revoked_at = revoked_at or datetime.now(UTC)
                session.flush()
                session.refresh(model)
            return model.to_dto()

    def touch_last_used(
        self,
        token_id: str,
        now: datetime | None = None,
    ) -> None:
        """Update last_used_at timestamp on successful token authentication."""
        with self._session_scope() as session:
            stmt = select(TenantApiTokenModel).where(TenantApiTokenModel.id == token_id)
            model = session.execute(stmt).scalar_one_or_none()
            if model is not None:
                model.last_used_at = now or datetime.now(UTC)
                session.flush()


class TenantApiTokenRepository(ApiTokenRepository):
    """Tenant-scoped repository for API tokens strictly enforcing tenant isolation."""

    def __init__(self, db_manager: DatabaseManager | Session, owner_id: str) -> None:
        super().__init__(db_manager)
        if not owner_id or not isinstance(owner_id, str):
            raise ValueError("owner_id must be a non-empty string")
        self.owner_id = owner_id

    def create_token(
        self,
        name: str,
        token_hash: str,
        prefix: str,
        expires_at: datetime | None = None,
        owner_id: str | None = None,
    ) -> ApiTokenResponse:
        return super().create_token(
            owner_id=self.owner_id,
            name=name,
            token_hash=token_hash,
            prefix=prefix,
            expires_at=expires_at,
        )

    def get_token(self, token_id: str) -> ApiTokenResponse | None:
        return super().get_token_by_id(token_id=token_id, owner_id=self.owner_id)

    def list_tokens(
        self,
        include_revoked: bool = True,
        owner_id: str | None = None,
    ) -> list[ApiTokenResponse]:
        return super().list_tokens(owner_id=self.owner_id, include_revoked=include_revoked)

    def revoke_token(
        self,
        token_id: str,
        owner_id: str | None = None,
    ) -> ApiTokenResponse | None:
        return super().revoke_token(token_id=token_id, owner_id=self.owner_id)
