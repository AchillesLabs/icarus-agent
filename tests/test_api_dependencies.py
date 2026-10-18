"""Tests for FastAPI dependency injection providers."""

from typing import Annotated

import pytest
from fastapi import APIRouter, Depends
from httpx import ASGITransport, AsyncClient
from icarus_api import ApiSettings, create_app
from icarus_core.persistence import (
    AgentRunRepository,
    DatabaseManager,
    MessageRepository,
    SessionRepository,
)
from sqlalchemy import text
from sqlalchemy.orm import Session


@pytest.mark.asyncio
async def test_dependency_injection_settings_and_overrides() -> None:
    """get_settings should resolve settings from app state and allow test overrides."""
    from icarus_api.dependencies import get_settings

    app = create_app(settings=ApiSettings(title="Custom Title", version="9.9.9"))
    router = APIRouter()

    @router.get("/check-settings")
    async def check_settings(
        settings: Annotated[ApiSettings, Depends(get_settings)],
    ) -> dict[str, str]:
        return {"title": settings.title, "version": settings.version}

    app.include_router(router)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/check-settings")
        assert resp.status_code == 200
        assert resp.json() == {"title": "Custom Title", "version": "9.9.9"}

        # Test dependency overrides
        app.dependency_overrides[get_settings] = lambda: ApiSettings(
            title="Overridden",
            version="0.0.1",
        )
        resp_overridden = await client.get("/check-settings")
        assert resp_overridden.json() == {"title": "Overridden", "version": "0.0.1"}


@pytest.mark.asyncio
async def test_dependency_injection_db_manager_and_session() -> None:
    """get_db_manager and get_db_session should inject working database resources."""
    from icarus_api.dependencies import get_db_manager, get_db_session

    db_manager = DatabaseManager("sqlite:///:memory:")
    app = create_app(db_manager=db_manager)
    router = APIRouter()

    @router.get("/check-db")
    async def check_db(
        manager: Annotated[DatabaseManager, Depends(get_db_manager)],
        session: Annotated[Session, Depends(get_db_session)],
    ) -> dict[str, int]:
        result = session.execute(text("SELECT 42")).scalar()
        return {
            "result": int(result) if result is not None else 0,
            "connected": int(manager.is_connected()),
        }

    app.include_router(router)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/check-db")
        assert resp.status_code == 200
        assert resp.json() == {"result": 42, "connected": 1}


@pytest.mark.asyncio
async def test_dependency_injection_repositories() -> None:
    """Repository dependencies should provide instances bound to the request database session."""
    from icarus_api.dependencies import (
        get_message_repository,
        get_run_repository,
        get_session_repository,
    )

    db_manager = DatabaseManager("sqlite:///:memory:")
    app = create_app(db_manager=db_manager)
    router = APIRouter()

    @router.get("/check-repos")
    async def check_repos(
        sess_repo: Annotated[SessionRepository, Depends(get_session_repository)],
        msg_repo: Annotated[MessageRepository, Depends(get_message_repository)],
        run_repo: Annotated[AgentRunRepository, Depends(get_run_repository)],
    ) -> dict[str, bool]:
        return {
            "session_repo_ok": isinstance(sess_repo, SessionRepository),
            "message_repo_ok": isinstance(msg_repo, MessageRepository),
            "run_repo_ok": isinstance(run_repo, AgentRunRepository),
        }

    app.include_router(router)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/check-repos")
        assert resp.status_code == 200
        assert resp.json() == {
            "session_repo_ok": True,
            "message_repo_ok": True,
            "run_repo_ok": True,
        }
