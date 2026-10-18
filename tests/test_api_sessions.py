"""Integration tests for RESTful session and message management API endpoints."""

import pytest
from httpx import ASGITransport, AsyncClient
from icarus_api import ApiSettings, create_app
from icarus_core.persistence import Base, DatabaseManager


@pytest.fixture
def app_with_db():
    db_manager = DatabaseManager("sqlite:///:memory:")
    Base.metadata.create_all(db_manager.engine)
    settings = ApiSettings(
        auth_tokens={
            "token-alice": "alice",
            "token-bob": "bob",
        }
    )
    app = create_app(settings=settings, db_manager=db_manager)
    return app


@pytest.mark.asyncio
async def test_session_lifecycle_crud_and_telemetry(app_with_db):
    """Full lifecycle: create session, inspect details, add messages, verify counts, delete."""
    alice_headers = {"Authorization": "Bearer token-alice"}

    transport = ASGITransport(app=app_with_db)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Create a new session
        create_resp = await client.post(
            "/v1/sessions",
            headers=alice_headers,
            json={"title": "Planning Sprint", "mode": "chat"},
        )
        assert create_resp.status_code == 201
        session_data = create_resp.json()
        assert session_data["title"] == "Planning Sprint"
        assert session_data["mode"] == "chat"
        assert session_data["owner_id"] == "alice"
        assert session_data["message_count"] == 0
        session_id = session_data["id"]

        # 2. Append a user message
        msg1_resp = await client.post(
            f"/v1/sessions/{session_id}/messages",
            headers=alice_headers,
            json={"role": "user", "content": "How do we implement authentication?"},
        )
        assert msg1_resp.status_code == 201
        msg1_data = msg1_resp.json()
        assert msg1_data["role"] == "user"
        assert msg1_data["content"] == "How do we implement authentication?"
        assert msg1_data["session_id"] == session_id
        assert msg1_data["token_estimate"] is not None

        # 3. Append an assistant message with tool call
        tool_call = {
            "id": "tc-1",
            "name": "grep_search",
            "arguments": {"query": "auth"},
        }
        msg2_resp = await client.post(
            f"/v1/sessions/{session_id}/messages",
            headers=alice_headers,
            json={
                "role": "assistant",
                "content": "Let me inspect the dependencies.",
                "tool_calls": [tool_call],
            },
        )
        assert msg2_resp.status_code == 201
        msg2_data = msg2_resp.json()
        assert msg2_data["role"] == "assistant"
        assert msg2_data["tool_calls"] is not None
        assert len(msg2_data["tool_calls"]) == 1

        # 4. Get transcript (GET /v1/sessions/{id}/messages)
        transcript_resp = await client.get(
            f"/v1/sessions/{session_id}/messages",
            headers=alice_headers,
        )
        assert transcript_resp.status_code == 200
        transcript = transcript_resp.json()
        assert len(transcript) == 2
        assert transcript[0]["role"] == "user"
        assert transcript[1]["role"] == "assistant"

        # 5. Get session details (GET /v1/sessions/{id}) verifying telemetry aggregates
        detail_resp = await client.get(
            f"/v1/sessions/{session_id}",
            headers=alice_headers,
        )
        assert detail_resp.status_code == 200
        details = detail_resp.json()
        assert details["id"] == session_id
        assert details["message_count"] == 2
        assert details["total_estimated_tokens"] > 0

        # 6. Delete session
        del_resp = await client.delete(
            f"/v1/sessions/{session_id}",
            headers=alice_headers,
        )
        assert del_resp.status_code == 200

        # 7. Confirm session is gone (404)
        get_gone = await client.get(
            f"/v1/sessions/{session_id}",
            headers=alice_headers,
        )
        assert get_gone.status_code == 404

        # 8. Confirm messages are cascaded and gone (404)
        msgs_gone = await client.get(
            f"/v1/sessions/{session_id}/messages",
            headers=alice_headers,
        )
        assert msgs_gone.status_code == 404


@pytest.mark.asyncio
async def test_session_pagination_and_sorting(app_with_db):
    """GET /v1/sessions supports limit, offset, and returns total count."""
    alice_headers = {"Authorization": "Bearer token-alice"}

    transport = ASGITransport(app=app_with_db)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Create 5 sessions
        for i in range(5):
            await client.post(
                "/v1/sessions",
                headers=alice_headers,
                json={"title": f"Session {i}"},
            )

        # Fetch first page (limit=2, offset=0)
        page1_resp = await client.get("/v1/sessions?limit=2&offset=0", headers=alice_headers)
        assert page1_resp.status_code == 200
        page1 = page1_resp.json()
        assert page1["total"] == 5
        assert len(page1["items"]) == 2
        assert page1["limit"] == 2
        assert page1["offset"] == 0

        # Fetch second page (limit=2, offset=2)
        page2_resp = await client.get("/v1/sessions?limit=2&offset=2", headers=alice_headers)
        assert page2_resp.status_code == 200
        page2 = page2_resp.json()
        assert page2["total"] == 5
        assert len(page2["items"]) == 2
        assert page2["offset"] == 2


@pytest.mark.asyncio
async def test_cross_tenant_session_isolation(app_with_db):
    """Bob cannot access or modify Alice's session or transcript."""
    alice_headers = {"Authorization": "Bearer token-alice"}
    bob_headers = {"Authorization": "Bearer token-bob"}

    transport = ASGITransport(app=app_with_db)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Alice creates a session
        create_resp = await client.post(
            "/v1/sessions",
            headers=alice_headers,
            json={"title": "Alice Confidential"},
        )
        session_id = create_resp.json()["id"]

        # Bob tries to read session -> 404
        resp_get = await client.get(f"/v1/sessions/{session_id}", headers=bob_headers)
        assert resp_get.status_code == 404

        # Bob tries to read messages -> 404
        resp_msgs = await client.get(
            f"/v1/sessions/{session_id}/messages",
            headers=bob_headers,
        )
        assert resp_msgs.status_code == 404

        # Bob tries to post message -> 404
        resp_post = await client.post(
            f"/v1/sessions/{session_id}/messages",
            headers=bob_headers,
            json={"content": "injection", "role": "user"},
        )
        assert resp_post.status_code == 404

        # Bob tries to delete session -> 404
        resp_del = await client.delete(f"/v1/sessions/{session_id}", headers=bob_headers)
        assert resp_del.status_code == 404


@pytest.mark.asyncio
async def test_unauthenticated_requests_rejected(app_with_db):
    """Unauthenticated requests to /v1/sessions return 401."""
    transport = ASGITransport(app=app_with_db)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        assert (await client.get("/v1/sessions")).status_code == 401
        assert (await client.post("/v1/sessions", json={"title": "Test"})).status_code == 401
        assert (await client.get("/v1/sessions/any-id")).status_code == 401
        assert (await client.get("/v1/sessions/any-id/messages")).status_code == 401
