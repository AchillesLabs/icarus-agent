"""Repository interfaces and implementations for session, message, and run entities."""

from datetime import UTC, datetime
from typing import Any

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
from sqlalchemy import delete, func, select

from icarus_core.persistence.database import DatabaseManager
from icarus_core.persistence.models import AgentRunModel, MessageModel, SessionModel
from icarus_core.tokens import TokenCounter, get_token_counter


class SessionRepository:
    """Repository handling CRUD operations and queries for conversation sessions."""

    def __init__(self, db_manager: DatabaseManager) -> None:
        self.db = db_manager

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
        with self.db.session_scope() as session:
            session.add(session_model)
            session.flush()
            session.refresh(session_model)
            return session_model.to_dto()

    def get_session(self, session_id: str, owner_id: str = "default") -> SessionDTO | None:
        """Retrieve a session by its ID and owner."""
        with self.db.session_scope() as session:
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
        with self.db.session_scope() as session:
            stmt = (
                select(SessionModel)
                .where(SessionModel.owner_id == owner_id)
                .order_by(SessionModel.updated_at.desc(), SessionModel.created_at.desc())
                .offset(offset)
                .limit(limit)
            )
            results = session.execute(stmt).scalars().all()
            return [model.to_dto() for model in results]

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
        with self.db.session_scope() as session:
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
        with self.db.session_scope() as session:
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
        with self.db.session_scope() as session:
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
        with self.db.session_scope() as session:
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


class MessageRepository:
    """Repository handling message appending and retrieval for conversation threads."""

    def __init__(
        self,
        db_manager: DatabaseManager,
        token_counter: TokenCounter | None = None,
    ) -> None:
        self.db = db_manager
        self._token_counter = token_counter

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
        with self.db.session_scope() as session:
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
        with self.db.session_scope() as session:
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
        with self.db.session_scope() as session:
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
        with self.db.session_scope() as session:
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
        with self.db.session_scope() as session:
            stmt = select(func.coalesce(func.sum(MessageModel.token_estimate), 0)).where(
                MessageModel.session_id == session_id,
                MessageModel.owner_id == owner_id,
            )
            return int(session.execute(stmt).scalar() or 0)


class AgentRunRepository:
    """Repository handling execution run registration and state updates."""

    def __init__(self, db_manager: DatabaseManager) -> None:
        self.db = db_manager

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
        with self.db.session_scope() as session:
            session.add(run_model)
            session.flush()
            session.refresh(run_model)
            return run_model.to_dto()

    def get_run(self, run_id: str, owner_id: str = "default") -> RunDTO | None:
        """Retrieve an agent run by ID and owner."""
        with self.db.session_scope() as session:
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
        with self.db.session_scope() as session:
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
        with self.db.session_scope() as session:
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
