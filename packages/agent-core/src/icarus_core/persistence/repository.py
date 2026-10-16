"""Repository interfaces and implementations for session, message, and run entities."""

from datetime import UTC, datetime

from icarus_contracts.session import (
    MessageCreate,
    MessageDTO,
    RunCreate,
    RunDTO,
    RunStatus,
    SessionCreate,
    SessionDTO,
    SessionUpdate,
)
from sqlalchemy import delete, select

from icarus_core.persistence.database import DatabaseManager
from icarus_core.persistence.models import AgentRunModel, MessageModel, SessionModel


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


class MessageRepository:
    """Repository handling message appending and retrieval for conversation threads."""

    def __init__(self, db_manager: DatabaseManager) -> None:
        self.db = db_manager

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
        msg_model = MessageModel(
            session_id=message_create.session_id,
            owner_id=effective_owner,
            role=role_value,
            content=message_create.content,
            token_estimate=message_create.token_estimate,
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
