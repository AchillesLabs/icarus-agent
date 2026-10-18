"""Integration tests for Server-Sent Events (SSE) agent run streaming and cancellation."""

import asyncio
import json

import pytest
from httpx import ASGITransport, AsyncClient
from icarus_api import ApiSettings, create_app
from icarus_contracts import ToolCall
from icarus_core.persistence import Base, DatabaseManager
from icarus_core.providers import ProviderRegistry
from icarus_core.providers.mock import MockProvider


def parse_sse_events(text: str) -> list[dict]:
    """Parse raw SSE text into a list of event dictionaries containing event and data."""
    events = []
    current_event = None
    current_data = []

    for line in text.split("\n"):
        line = line.strip("\r")
        if not line:
            if current_event or current_data:
                data_str = "\n".join(current_data)
                try:
                    data_obj = json.loads(data_str)
                except Exception:
                    data_obj = data_str
                events.append({"event": current_event, "data": data_obj})
                current_event = None
                current_data = []
            continue

        if line.startswith("event:"):
            current_event = line.partition("event:")[2].strip()
        elif line.startswith("data:"):
            current_data.append(line.partition("data:")[2].strip())

    if current_event or current_data:
        data_str = "\n".join(current_data)
        try:
            data_obj = json.loads(data_str)
        except Exception:
            data_obj = data_str
        events.append({"event": current_event, "data": data_obj})

    return events


@pytest.fixture
def test_setup():
    db_manager = DatabaseManager("sqlite:///:memory:")
    Base.metadata.create_all(db_manager.engine)
    settings = ApiSettings(
        auth_tokens={
            "token-alice": "alice",
            "token-bob": "bob",
        }
    )

    provider_registry = ProviderRegistry()
    mock_provider = MockProvider(
        responses=["The capital of France is Paris."],
        canned_chunks=["The capital ", "of France ", "is Paris."],
    )
    provider_registry.register("mock", lambda **kw: mock_provider, requires_credentials=False)

    app = create_app(
        settings=settings,
        db_manager=db_manager,
        provider_registry=provider_registry,
    )
    return {
        "app": app,
        "db_manager": db_manager,
        "mock_provider": mock_provider,
        "provider_registry": provider_registry,
    }


@pytest.mark.asyncio
async def test_sse_run_streaming_full_sequence(test_setup):
    """Verify SSE streaming delivers turn_start, token deltas, and run_completed in order."""
    app = test_setup["app"]
    alice_headers = {"Authorization": "Bearer token-alice"}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Create a session
        sess_resp = await client.post(
            "/v1/sessions",
            headers=alice_headers,
            json={"title": "Geography Trivia"},
        )
        assert sess_resp.status_code == 201
        session_id = sess_resp.json()["id"]

        # 2. Initiate SSE streaming run
        async with client.stream(
            "POST",
            f"/v1/sessions/{session_id}/runs/stream",
            headers=alice_headers,
            json={"prompt": "What is the capital of France?"},
        ) as response:
            assert response.status_code == 200
            assert "text/event-stream" in response.headers["content-type"]

            raw_body = ""
            async for chunk in response.aiter_text():
                raw_body += chunk

        events = parse_sse_events(raw_body)
        assert len(events) >= 3

        event_types = [ev["event"] for ev in events]
        assert "turn_start" in event_types
        assert "token" in event_types
        assert "run_completed" in event_types

        # Verify event order: turn_start must precede token, which must precede run_completed
        turn_start_idx = event_types.index("turn_start")
        token_idx = event_types.index("token")
        completed_idx = event_types.index("run_completed")
        assert turn_start_idx < token_idx < completed_idx

        # Verify token content
        tokens = [ev["data"]["delta"] for ev in events if ev["event"] == "token"]
        reconstructed = "".join(tokens)
        assert "The capital of France is Paris." in reconstructed

        # Verify run_completed payload
        completed_ev = events[completed_idx]
        assert completed_ev["data"]["status"] == "succeeded"
        assert completed_ev["data"]["result"] == "The capital of France is Paris."
        run_id = completed_ev["data"]["run_id"]
        assert run_id is not None

        # Verify run state in database via GET /v1/runs/{run_id}
        run_resp = await client.get(f"/v1/runs/{run_id}", headers=alice_headers)
        assert run_resp.status_code == 200
        run_data = run_resp.json()
        assert run_data["status"] == "succeeded"
        assert run_data["session_id"] == session_id
        assert run_data["owner_id"] == "alice"
        assert run_data["completed_at"] is not None

        # Verify message transcript in database
        msg_resp = await client.get(
            f"/v1/sessions/{session_id}/messages",
            headers=alice_headers,
        )
        assert msg_resp.status_code == 200
        messages = msg_resp.json()
        assert len(messages) == 2
        assert messages[0]["role"] == "user"
        assert messages[0]["content"] == "What is the capital of France?"
        assert messages[1]["role"] == "assistant"
        assert messages[1]["content"] == "The capital of France is Paris."


@pytest.mark.asyncio
async def test_sse_streaming_with_tool_execution(test_setup):
    """Verify tool_start and tool_end events stream properly when tools are called."""
    app = test_setup["app"]
    provider_registry = test_setup["provider_registry"]
    alice_headers = {"Authorization": "Bearer token-alice"}

    tool_call = ToolCall(
        id="call-42",
        name="read_file",
        arguments={"path": "README.md"},
    )
    mock_provider = MockProvider(
        responses=["File contents inspected."],
        canned_chunks=["File ", "contents ", "inspected."],
        tool_calls_sequence=[[tool_call], None],
    )
    provider_registry.register("mock-tool", lambda **kw: mock_provider, requires_credentials=False)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        sess_resp = await client.post(
            "/v1/sessions",
            headers=alice_headers,
            json={"title": "Tool Session"},
        )
        session_id = sess_resp.json()["id"]

        async with client.stream(
            "POST",
            f"/v1/sessions/{session_id}/runs/stream",
            headers=alice_headers,
            json={"prompt": "Inspect README", "provider": "mock-tool", "auto_approve": True},
        ) as response:
            assert response.status_code == 200
            raw_body = ""
            async for chunk in response.aiter_text():
                raw_body += chunk

        events = parse_sse_events(raw_body)
        event_types = [ev["event"] for ev in events]

        assert "tool_start" in event_types
        assert "tool_end" in event_types
        assert "run_completed" in event_types

        tool_start_ev = next(ev for ev in events if ev["event"] == "tool_start")
        assert tool_start_ev["data"]["tool_name"] == "read_file"
        assert tool_start_ev["data"]["tool_call_id"] == "call-42"

        tool_end_ev = next(ev for ev in events if ev["event"] == "tool_end")
        assert tool_end_ev["data"]["tool_name"] == "read_file"
        assert tool_end_ev["data"]["tool_call_id"] == "call-42"


@pytest.mark.asyncio
async def test_sse_streaming_run_cancellation_mid_flight(test_setup):
    """Verify POST /v1/runs/{id}/cancel cleanly halts an active run and emits run_cancelled."""
    app = test_setup["app"]
    provider_registry = test_setup["provider_registry"]
    alice_headers = {"Authorization": "Bearer token-alice"}

    from icarus_contracts.provider import StreamChunk

    started_event = asyncio.Event()

    class CancellableMockProvider(MockProvider):
        async def stream(self, messages, **kwargs):
            yield StreamChunk(delta="Chunk 1 ")
            started_event.set()
            await asyncio.sleep(10.0)
            yield StreamChunk(delta="Never reached")

    slow_provider = CancellableMockProvider()
    provider_registry.register("slow-mock", lambda **kw: slow_provider, requires_credentials=False)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        sess_resp = await client.post(
            "/v1/sessions",
            headers=alice_headers,
            json={"title": "Cancellation Session"},
        )
        session_id = sess_resp.json()["id"]

        run_id_future: asyncio.Future[str] = asyncio.get_running_loop().create_future()
        events_collected = []

        async def _stream_reader():
            async with client.stream(
                "POST",
                f"/v1/sessions/{session_id}/runs/stream",
                headers=alice_headers,
                json={"prompt": "Tell me a long story", "provider": "slow-mock"},
            ) as response:
                assert response.status_code == 200
                buffer = ""
                async for chunk in response.aiter_text():
                    buffer += chunk
                    # Parse on the fly to capture run_id
                    parsed = parse_sse_events(buffer)
                    for ev in parsed:
                        if not run_id_future.done():
                            rid = ev.get("data", {}).get("run_id")
                            if rid:
                                run_id_future.set_result(rid)
                events_collected.extend(parse_sse_events(buffer))

        # Start stream reader
        stream_task = asyncio.create_task(_stream_reader())

        # Wait until provider has started and entered sleep
        await asyncio.wait_for(started_event.wait(), timeout=2.0)

        # Retrieve active run_id via API
        runs_resp = await client.get(
            f"/v1/sessions/{session_id}/runs",
            headers=alice_headers,
        )
        assert runs_resp.status_code == 200
        runs = runs_resp.json()
        assert len(runs) >= 1
        run_id = runs[0]["id"]

        # Cancel the run via API
        cancel_resp = await client.post(
            f"/v1/runs/{run_id}/cancel",
            headers=alice_headers,
        )
        assert cancel_resp.status_code == 200
        cancel_data = cancel_resp.json()
        assert cancel_data["cancelled"] is True
        assert cancel_data["status"] == "cancelled"

        # Wait for streaming task to terminate cleanly
        await asyncio.wait_for(stream_task, timeout=3.0)

        # Verify run_cancelled event was emitted
        event_types = [ev["event"] for ev in events_collected]
        assert "run_cancelled" in event_types

        # Verify run in DB is marked cancelled
        run_resp = await client.get(f"/v1/runs/{run_id}", headers=alice_headers)
        assert run_resp.status_code == 200
        assert run_resp.json()["status"] == "cancelled"


@pytest.mark.asyncio
async def test_cancel_completed_and_nonexistent_run(test_setup):
    """Cancelling a completed run returns cancelled=False; non-existent returns 404."""
    app = test_setup["app"]
    alice_headers = {"Authorization": "Bearer token-alice"}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. 404 for non-existent run
        non_existent = await client.post(
            "/v1/runs/does-not-exist/cancel",
            headers=alice_headers,
        )
        assert non_existent.status_code == 404

        # 2. Run a fast completed run
        sess_resp = await client.post(
            "/v1/sessions",
            headers=alice_headers,
            json={"title": "Fast Session"},
        )
        session_id = sess_resp.json()["id"]

        async with client.stream(
            "POST",
            f"/v1/sessions/{session_id}/runs/stream",
            headers=alice_headers,
            json={"prompt": "Fast run"},
        ) as response:
            body = ""
            async for chunk in response.aiter_text():
                body += chunk

        events = parse_sse_events(body)
        comp_ev = next(ev for ev in events if ev["event"] == "run_completed")
        run_id = comp_ev["data"]["run_id"]

        # 3. Cancel already completed run -> returns 200 with cancelled=False
        cancel_again = await client.post(
            f"/v1/runs/{run_id}/cancel",
            headers=alice_headers,
        )
        assert cancel_again.status_code == 200
        res = cancel_again.json()
        assert res["cancelled"] is False
        assert "already" in res["message"].lower()


@pytest.mark.asyncio
async def test_tenant_isolation_on_streaming_and_cancellation(test_setup):
    """Ensure cross-tenant streaming, inspection, and cancellation are rejected with 404."""
    app = test_setup["app"]
    alice_headers = {"Authorization": "Bearer token-alice"}
    bob_headers = {"Authorization": "Bearer token-bob"}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Alice creates a session
        sess_resp = await client.post(
            "/v1/sessions",
            headers=alice_headers,
            json={"title": "Alice Confidential"},
        )
        alice_session_id = sess_resp.json()["id"]

        # Bob attempts to stream a run on Alice's session -> 404
        bob_stream = await client.post(
            f"/v1/sessions/{alice_session_id}/runs/stream",
            headers=bob_headers,
            json={"prompt": "Bob spying"},
        )
        assert bob_stream.status_code == 404

        # Alice runs a session
        async with client.stream(
            "POST",
            f"/v1/sessions/{alice_session_id}/runs/stream",
            headers=alice_headers,
            json={"prompt": "Alice's task"},
        ) as response:
            body = ""
            async for chunk in response.aiter_text():
                body += chunk
        events = parse_sse_events(body)
        comp_ev = next(ev for ev in events if ev["event"] == "run_completed")
        alice_run_id = comp_ev["data"]["run_id"]

        # Bob attempts to inspect Alice's run -> 404
        bob_inspect = await client.get(
            f"/v1/runs/{alice_run_id}",
            headers=bob_headers,
        )
        assert bob_inspect.status_code == 404

        # Bob attempts to cancel Alice's run -> 404
        bob_cancel = await client.post(
            f"/v1/runs/{alice_run_id}/cancel",
            headers=bob_headers,
        )
        assert bob_cancel.status_code == 404


@pytest.mark.asyncio
async def test_unauthenticated_requests_rejected(test_setup):
    """Unauthenticated calls must return 401/403."""
    app = test_setup["app"]
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r1 = await client.post("/v1/sessions/any-session/runs/stream")
        assert r1.status_code in (401, 403)

        r2 = await client.post("/v1/runs/any-run/cancel")
        assert r2.status_code in (401, 403)


@pytest.mark.asyncio
async def test_run_failure_emits_run_failed(test_setup):
    """When provider raises an error, stream emits run_failed and marks run failed in DB."""
    app = test_setup["app"]
    provider_registry = test_setup["provider_registry"]
    alice_headers = {"Authorization": "Bearer token-alice"}

    failing_provider = MockProvider(
        should_fail=RuntimeError("Provider outage 500"),
    )
    provider_registry.register(
        "failing-mock", lambda **kw: failing_provider, requires_credentials=False
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        sess_resp = await client.post(
            "/v1/sessions",
            headers=alice_headers,
            json={"title": "Failing Session"},
        )
        session_id = sess_resp.json()["id"]

        async with client.stream(
            "POST",
            f"/v1/sessions/{session_id}/runs/stream",
            headers=alice_headers,
            json={"prompt": "Will fail", "provider": "failing-mock"},
        ) as response:
            assert response.status_code == 200
            body = ""
            async for chunk in response.aiter_text():
                body += chunk

        events = parse_sse_events(body)
        failed_ev = next(ev for ev in events if ev["event"] == "run_failed")
        assert failed_ev["data"]["status"] == "failed"
        assert "Provider outage 500" in failed_ev["data"]["error"]

        run_id = failed_ev["data"]["run_id"]
        run_resp = await client.get(f"/v1/runs/{run_id}", headers=alice_headers)
        assert run_resp.status_code == 200
        assert run_resp.json()["status"] == "failed"


@pytest.mark.asyncio
async def test_sse_streaming_compaction_event(test_setup):
    """Verify compaction event is emitted in SSE stream when history exceeds budget."""
    from icarus_contracts.provider import ProviderCapabilities

    app = test_setup["app"]
    provider_registry = test_setup["provider_registry"]
    alice_headers = {"Authorization": "Bearer token-alice"}

    class SmallContextMockProvider(MockProvider):
        def get_capabilities(self, model: str | None = None) -> ProviderCapabilities:
            return ProviderCapabilities(
                supported_models=["mock-model"],
                max_context_tokens=8000,  # 8000 window -> 2000 input budget, trigger at 1600 tokens
                supports_streaming=True,
                supports_tools=True,
            )

    provider_registry.register(
        "small-ctx", lambda **kw: SmallContextMockProvider(), requires_credentials=False
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        sess_resp = await client.post(
            "/v1/sessions",
            headers=alice_headers,
            json={"title": "Compaction Session"},
        )
        session_id = sess_resp.json()["id"]

        # Put heavy content in older turn so it gets compacted
        heavy_content = "Important debugging log line with error code 500\n" * 300
        await client.post(
            f"/v1/sessions/{session_id}/messages",
            headers=alice_headers,
            json={"role": "user", "content": f"Logs:\n{heavy_content}"},
        )
        await client.post(
            f"/v1/sessions/{session_id}/messages",
            headers=alice_headers,
            json={"role": "assistant", "content": "Acknowledged logs."},
        )

        # Seed recent turns that will be retained
        await client.post(
            f"/v1/sessions/{session_id}/messages",
            headers=alice_headers,
            json={"role": "user", "content": "How are servers performing now?"},
        )
        await client.post(
            f"/v1/sessions/{session_id}/messages",
            headers=alice_headers,
            json={"role": "assistant", "content": "Recent turns are healthy."},
        )
        await client.post(
            f"/v1/sessions/{session_id}/messages",
            headers=alice_headers,
            json={"role": "user", "content": "Are there any lingering alerts?"},
        )
        await client.post(
            f"/v1/sessions/{session_id}/messages",
            headers=alice_headers,
            json={"role": "assistant", "content": "No lingering alerts detected."},
        )

        async with client.stream(
            "POST",
            f"/v1/sessions/{session_id}/runs/stream",
            headers=alice_headers,
            json={"prompt": "Summarize conclusions", "provider": "small-ctx", "auto_compact": True},
        ) as response:
            assert response.status_code == 200
            body = ""
            async for chunk in response.aiter_text():
                body += chunk

        events = parse_sse_events(body)
        event_types = [ev["event"] for ev in events]

        assert "compaction" in event_types
        comp_ev = next(ev for ev in events if ev["event"] == "compaction")
        assert comp_ev["data"]["tokens_saved"] > 0
        assert comp_ev["data"]["original_message_count"] > 0
