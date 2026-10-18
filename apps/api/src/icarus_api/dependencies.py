"""Dependency injection providers for FastAPI routes."""

from collections.abc import Generator
from typing import Annotated

from fastapi import Depends, Request
from icarus_core.persistence import (
    AgentRunRepository,
    DatabaseManager,
    MessageRepository,
    SessionRepository,
)
from sqlalchemy.orm import Session

from icarus_api.config import ApiSettings


def get_settings(request: Request) -> ApiSettings:
    """Resolve active application settings from request state."""
    settings = getattr(request.app.state, "settings", None)
    if settings is None:
        settings = ApiSettings()
        request.app.state.settings = settings
    return settings


def get_db_manager(request: Request) -> DatabaseManager:
    """Resolve active DatabaseManager from request state."""
    db_manager = getattr(request.app.state, "db_manager", None)
    if db_manager is None:
        settings = get_settings(request)
        db_manager = DatabaseManager(db_url=settings.database_url)
        request.app.state.db_manager = db_manager
    return db_manager


def get_db_session(
    db_manager: Annotated[DatabaseManager, Depends(get_db_manager)],
) -> Generator[Session, None, None]:
    """Provide a transactional session scope for the duration of a request."""
    with db_manager.session_scope() as session:
        yield session


def get_session_repository(
    session: Annotated[Session, Depends(get_db_session)],
) -> SessionRepository:
    """Provide a SessionRepository bound to the current request's session."""
    return SessionRepository(session)


def get_message_repository(
    session: Annotated[Session, Depends(get_db_session)],
) -> MessageRepository:
    """Provide a MessageRepository bound to the current request's session."""
    return MessageRepository(session)


def get_run_repository(
    session: Annotated[Session, Depends(get_db_session)],
) -> AgentRunRepository:
    """Provide an AgentRunRepository bound to the current request's session."""
    return AgentRunRepository(session)
