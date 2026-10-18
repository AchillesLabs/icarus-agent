"""Security integration tests for Bearer authentication and tenant-isolated request scoping."""

from typing import Annotated

import pytest
from fastapi import APIRouter, Depends, HTTPException
from httpx import ASGITransport, AsyncClient
from icarus_api import (
    ApiSettings,
    create_app,
    get_current_tenant,
    get_tenant_db_session,
    get_tenant_message_repository,
    get_tenant_run_repository,
    get_tenant_session,
    get_tenant_session_repository,
)
from icarus_contracts import (
    MessageCreate,
    MessageDTO,
    MessageRole,
    RunCreate,
    RunDTO,
    RunStatus,
    SessionCreate,
    SessionDTO,
    TenantIdentity,
)
from icarus_core.persistence import (
    Base,
    DatabaseManager,
    TenantMessageRepository,
    TenantRunRepository,
    TenantSessionRepository,
)
from pydantic import BaseModel
from sqlalchemy.orm import Session


class CreateSessionBody(BaseModel):
    title: str = "New Session"
    mode: str = "chat"
    owner_id: str | None = None


class CreateMessageBody(BaseModel):
    content: str
    role: str = "user"


class CreateRunBody(BaseModel):
    provider: str = "grok"
    model: str = "grok-2"


def build_test_router() -> APIRouter:
    router = APIRouter(prefix="/v1")

    @router.post("/sessions", response_model=SessionDTO)
    async def create_session(
        body: CreateSessionBody,
        repo: Annotated[TenantSessionRepository, Depends(get_tenant_session_repository)],
    ) -> SessionDTO:
        # Pass body to repo; repo must enforce authenticated tenant owner_id
        return repo.create_session(
            SessionCreate(
                title=body.title,
                mode=body.mode,
                owner_id=body.owner_id or "unspecified",
            )
        )

    @router.get("/sessions", response_model=list[SessionDTO])
    async def list_sessions(
        repo: Annotated[TenantSessionRepository, Depends(get_tenant_session_repository)],
    ) -> list[SessionDTO]:
        return repo.list_sessions()

    @router.get("/sessions/{session_id}", response_model=SessionDTO)
    async def get_session(
        session: Annotated[SessionDTO, Depends(get_tenant_session)],
    ) -> SessionDTO:
        return session

    @router.delete("/sessions/{session_id}")
    async def delete_session(
        session_id: str,
        repo: Annotated[TenantSessionRepository, Depends(get_tenant_session_repository)],
    ) -> dict[str, bool]:
        deleted = repo.delete_session(session_id)
        if not deleted:
            raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")
        return {"deleted": True}

    @router.post("/sessions/{session_id}/messages", response_model=MessageDTO)
    async def create_message(
        session_id: str,
        body: CreateMessageBody,
        msg_repo: Annotated[TenantMessageRepository, Depends(get_tenant_message_repository)],
    ) -> MessageDTO:
        return msg_repo.create_message(
            MessageCreate(
                session_id=session_id,
                content=body.content,
                role=MessageRole(body.role),
            )
        )

    @router.post("/sessions/{session_id}/runs", response_model=RunDTO)
    async def create_run(
        session_id: str,
        body: CreateRunBody,
        run_repo: Annotated[TenantRunRepository, Depends(get_tenant_run_repository)],
    ) -> RunDTO:
        return run_repo.create_run(
            RunCreate(
                session_id=session_id,
                status=RunStatus.RUNNING,
                provider=body.provider,
                model=body.model,
            )
        )

    @router.get("/tenant-session-info")
    async def tenant_session_info(
        tenant: Annotated[TenantIdentity, Depends(get_current_tenant)],
        db_session: Annotated[Session, Depends(get_tenant_db_session)],
    ) -> dict[str, str]:
        return {
            "identity_owner_id": tenant.owner_id,
            "session_info_owner_id": db_session.info.get("owner_id", ""),
        }

    return router


@pytest.fixture
def auth_test_setup():
    db_manager = DatabaseManager("sqlite:///:memory:")
    Base.metadata.create_all(db_manager.engine)
    settings = ApiSettings(
        auth_tokens={
            "token-alice": "alice",
            "token-bob": "bob",
        }
    )
    app = create_app(settings=settings, db_manager=db_manager)
    app.include_router(build_test_router())
    return app, db_manager


@pytest.mark.asyncio
async def test_unauthenticated_request_returns_401_with_standard_schema(auth_test_setup):
    app, _ = auth_test_setup
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/v1/sessions")
        assert resp.status_code == 401
        data = resp.json()
        assert "error" in data
        assert data["error"]["code"] == "unauthorized"
        assert "credentials" in data["error"]["message"].lower()
        assert resp.headers.get("www-authenticate") == "Bearer"


@pytest.mark.asyncio
async def test_invalid_bearer_token_returns_401_with_standard_schema(auth_test_setup):
    app, _ = auth_test_setup
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(
            "/v1/sessions", headers={"Authorization": "Bearer fraudulent-token"}
        )
        assert resp.status_code == 401
        data = resp.json()
        assert data["error"]["code"] == "unauthorized"
        assert "invalid" in data["error"]["message"].lower()
        assert resp.headers.get("www-authenticate") == "Bearer"


@pytest.mark.asyncio
async def test_cross_tenant_session_isolation(auth_test_setup):
    """Alice creates a session; Bob is rejected with HTTP 404 when querying or deleting it."""
    app, _ = auth_test_setup
    alice_headers = {"Authorization": "Bearer token-alice"}
    bob_headers = {"Authorization": "Bearer token-bob"}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Alice creates a session
        create_resp = await client.post(
            "/v1/sessions",
            headers=alice_headers,
            json={"title": "Alice Secret Project", "mode": "chat"},
        )
        assert create_resp.status_code == 200
        alice_session = create_resp.json()
        session_id = alice_session["id"]
        assert alice_session["owner_id"] == "alice"

        # 2. Alice can retrieve her session
        get_alice_resp = await client.get(f"/v1/sessions/{session_id}", headers=alice_headers)
        assert get_alice_resp.status_code == 200
        assert get_alice_resp.json()["id"] == session_id

        # 3. Bob attempts to retrieve Alice's session -> MUST fail with 404
        get_bob_resp = await client.get(f"/v1/sessions/{session_id}", headers=bob_headers)
        assert get_bob_resp.status_code == 404
        data = get_bob_resp.json()
        assert data["error"]["code"] == "not_found"

        # 4. Bob lists sessions -> Alice's session is NOT visible
        list_bob_resp = await client.get("/v1/sessions", headers=bob_headers)
        assert list_bob_resp.status_code == 200
        bob_sessions = list_bob_resp.json()
        assert all(s["id"] != session_id for s in bob_sessions)

        # 5. Bob attempts to delete Alice's session -> MUST fail with 404
        del_bob_resp = await client.delete(f"/v1/sessions/{session_id}", headers=bob_headers)
        assert del_bob_resp.status_code == 404

        # 6. Session still exists for Alice
        still_there = await client.get(f"/v1/sessions/{session_id}", headers=alice_headers)
        assert still_there.status_code == 200


@pytest.mark.asyncio
async def test_cross_tenant_mutation_rejection(auth_test_setup):
    """Bob attempting to add messages or runs to Alice's session fails with 403 Forbidden."""
    app, _ = auth_test_setup
    alice_headers = {"Authorization": "Bearer token-alice"}
    bob_headers = {"Authorization": "Bearer token-bob"}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Alice creates a session
        create_resp = await client.post(
            "/v1/sessions",
            headers=alice_headers,
            json={"title": "Alice Private Session"},
        )
        session_id = create_resp.json()["id"]

        # Bob attempts to append a message to Alice's session -> 403 Forbidden
        msg_resp = await client.post(
            f"/v1/sessions/{session_id}/messages",
            headers=bob_headers,
            json={"content": "Malicious payload injection", "role": "user"},
        )
        assert msg_resp.status_code == 403
        data = msg_resp.json()
        assert data["error"]["code"] == "forbidden"
        assert "cross-tenant" in data["error"]["message"].lower()

        # Bob attempts to start a run in Alice's session -> 403 Forbidden
        run_resp = await client.post(
            f"/v1/sessions/{session_id}/runs",
            headers=bob_headers,
            json={"provider": "grok", "model": "grok-2"},
        )
        assert run_resp.status_code == 403
        run_data = run_resp.json()
        assert run_data["error"]["code"] == "forbidden"


@pytest.mark.asyncio
async def test_payload_owner_id_override_rejected(auth_test_setup):
    """If a client provides an owner_id in the JSON body,
    it is strictly overridden by the authenticated identity.
    """
    app, _ = auth_test_setup
    alice_headers = {"Authorization": "Bearer token-alice"}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/v1/sessions",
            headers=alice_headers,
            json={"title": "Forged Owner Attempt", "owner_id": "bob"},
        )
        assert resp.status_code == 200
        # The resulting session must be bound to alice, never bob
        assert resp.json()["owner_id"] == "alice"


@pytest.mark.asyncio
async def test_tenant_db_session_info_bound(auth_test_setup):
    """get_tenant_db_session should bind tenant identity to session info."""
    app, _ = auth_test_setup
    alice_headers = {"Authorization": "Bearer token-alice"}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/v1/tenant-session-info", headers=alice_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["identity_owner_id"] == "alice"
        assert data["session_info_owner_id"] == "alice"
