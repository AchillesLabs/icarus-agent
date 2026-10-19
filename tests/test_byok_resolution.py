"""Integration tests for dynamic BYOK provider resolution, ephemeral secret injection,
and zero-leak security invariants in remote agent runs.
"""

import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from icarus_api import ApiSettings, create_app
from icarus_contracts import (
    CompletionResult,
    PromptMessage,
    ProviderCapabilities,
    StreamChunk,
)
from icarus_contracts.jobs import ScheduledJobCreate
from icarus_core.persistence import Base, DatabaseManager, ScheduledJobRepository
from icarus_core.providers import ModelProvider, ProviderRegistry
from icarus_core.security import CredentialVault
from icarus_worker.config import WorkerSettings
from icarus_worker.daemon import WorkerDaemon


class CapturingMockProvider(ModelProvider):
    """Mock provider capturing the ephemeral api_key passed to it upon instantiation."""

    def __init__(
        self,
        api_key: str | None = None,
        responses: list[str] | None = None,
        raise_on_complete: Exception | None = None,
    ) -> None:
        self.api_key = api_key
        self.responses = responses or ["Mock BYOK completion result."]
        self.raise_on_complete = raise_on_complete
        self.recorded_calls: list[list[PromptMessage]] = []

    async def generate(
        self,
        messages: list[PromptMessage],
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        tools: list[dict[str, Any]] | None = None,
    ) -> CompletionResult:
        if self.raise_on_complete is not None:
            raise self.raise_on_complete
        self.recorded_calls.append(messages)
        content = self.responses[0]
        return CompletionResult(
            content=content,
            model=model or "mock-byok-model",
            finish_reason="stop",
            prompt_tokens=20,
            completion_tokens=10,
        )

    async def stream(
        self,
        messages: list[PromptMessage],
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[StreamChunk]:
        if self.raise_on_complete is not None:
            raise self.raise_on_complete
        self.recorded_calls.append(messages)
        yield StreamChunk(delta=self.responses[0], finish_reason="stop")

    def get_capabilities(self, model: str | None = None) -> ProviderCapabilities:
        return ProviderCapabilities(supports_streaming=True, supports_tool_calling=True)


def parse_sse_events(text: str) -> list[dict[str, Any]]:
    """Parse raw SSE text into typed event dictionaries."""
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
def byok_env():
    """Isolated environment with database, credential vault, and capturing providers."""
    db_manager = DatabaseManager("sqlite:///:memory:")
    Base.metadata.create_all(db_manager.engine)

    vault = CredentialVault(master_key="test-master-vault-key-32b-length!!")
    provider_registry = ProviderRegistry()

    captured_providers: list[CapturingMockProvider] = []

    def _openrouter_factory(api_key: str | None = None, **kw: Any) -> ModelProvider:
        prov = CapturingMockProvider(api_key=api_key, **kw)
        captured_providers.append(prov)
        return prov

    provider_registry.register("openrouter", _openrouter_factory, requires_credentials=True)

    def _groq_factory(api_key: str | None = None, **kw: Any) -> ModelProvider:
        prov = CapturingMockProvider(api_key=api_key, **kw)
        captured_providers.append(prov)
        return prov

    provider_registry.register("groq", _groq_factory, requires_credentials=True)

    settings = ApiSettings(
        auth_tokens={
            "token-alice": "alice",
            "token-bob": "bob",
        },
        allow_fallback_to_system_credentials=True,
    )

    app = create_app(
        settings=settings,
        db_manager=db_manager,
        provider_registry=provider_registry,
        credential_vault=vault,
    )

    return {
        "app": app,
        "db_manager": db_manager,
        "vault": vault,
        "provider_registry": provider_registry,
        "captured_providers": captured_providers,
        "settings": settings,
    }


@pytest.mark.asyncio
async def test_dynamic_byok_injection_in_sse_streaming_run(byok_env):
    """Verify tenant decrypted vault key is ephemerally injected during SSE runs."""
    app = byok_env["app"]
    alice_headers = {"Authorization": "Bearer token-alice"}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Register a BYOK key in Alice's vault for provider 'openrouter'
        secret_key = "sk-or-v1-alice-secret-streaming-12345"
        vault_resp = await client.post(
            "/v1/vault/credentials",
            headers=alice_headers,
            json={"provider": "openrouter", "api_key": secret_key},
        )
        assert vault_resp.status_code == 201

        # 2. Create a session
        sess_resp = await client.post(
            "/v1/sessions",
            headers=alice_headers,
            json={"title": "Streaming BYOK Session"},
        )
        session_id = sess_resp.json()["id"]

        # 3. Stream agent run requesting provider 'openrouter'
        async with client.stream(
            "POST",
            f"/v1/sessions/{session_id}/runs/stream",
            headers=alice_headers,
            json={"prompt": "Hello BYOK!", "provider": "openrouter"},
        ) as stream_resp:
            assert stream_resp.status_code == 200
            raw_text = ""
            async for chunk in stream_resp.aiter_text():
                raw_text += chunk

        events = parse_sse_events(raw_text)
        completed_events = [e for e in events if e["event"] == "run_completed"]
        assert len(completed_events) == 1
        assert completed_events[0]["data"]["status"] == "succeeded"

        # Verify that the provider was instantiated with Alice's decrypted secret
        assert len(byok_env["captured_providers"]) >= 1
        active_prov = byok_env["captured_providers"][-1]
        assert active_prov.api_key == secret_key


@pytest.mark.asyncio
async def test_dynamic_byok_injection_in_one_shot_run(byok_env):
    """Verify tenant vault key is ephemerally injected during synchronous one-shot runs."""
    app = byok_env["app"]
    alice_headers = {"Authorization": "Bearer token-alice"}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        secret_key = "sk-or-v1-alice-secret-oneshot-67890"
        await client.post(
            "/v1/vault/credentials",
            headers=alice_headers,
            json={"provider": "openrouter", "api_key": secret_key},
        )

        sess_resp = await client.post(
            "/v1/sessions",
            headers=alice_headers,
            json={"title": "OneShot BYOK Session"},
        )
        session_id = sess_resp.json()["id"]

        # Run one-shot execution
        run_resp = await client.post(
            f"/v1/sessions/{session_id}/runs",
            headers=alice_headers,
            json={"prompt": "One shot prompt", "provider": "openrouter"},
        )
        assert run_resp.status_code == 201
        run_data = run_resp.json()
        assert run_data["status"] == "succeeded"
        assert run_data["provider"] == "openrouter"

        # Check provider got Alice's key
        active_prov = byok_env["captured_providers"][-1]
        assert active_prov.api_key == secret_key


@pytest.mark.asyncio
async def test_cross_tenant_byok_isolation(byok_env):
    """Verify Alice and Bob receive only their own respective vault keys for same provider."""
    app = byok_env["app"]
    alice_headers = {"Authorization": "Bearer token-alice"}
    bob_headers = {"Authorization": "Bearer token-bob"}

    alice_key = "sk-groq-alice-unique-key-11111"
    bob_key = "sk-groq-bob-unique-key-22222"

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Register keys
        await client.post(
            "/v1/vault/credentials",
            headers=alice_headers,
            json={"provider": "groq", "api_key": alice_key},
        )
        await client.post(
            "/v1/vault/credentials",
            headers=bob_headers,
            json={"provider": "groq", "api_key": bob_key},
        )

        # Alice creates session & runs
        sess_a = (
            await client.post(
                "/v1/sessions",
                headers=alice_headers,
                json={"title": "Alice Session"},
            )
        ).json()["id"]
        run_a = await client.post(
            f"/v1/sessions/{sess_a}/runs",
            headers=alice_headers,
            json={"prompt": "Alice query", "provider": "groq"},
        )
        assert run_a.status_code == 201
        prov_alice = byok_env["captured_providers"][-1]
        assert prov_alice.api_key == alice_key

        # Bob creates session & runs
        sess_b = (
            await client.post(
                "/v1/sessions",
                headers=bob_headers,
                json={"title": "Bob Session"},
            )
        ).json()["id"]
        run_b = await client.post(
            f"/v1/sessions/{sess_b}/runs",
            headers=bob_headers,
            json={"prompt": "Bob query", "provider": "groq"},
        )
        assert run_b.status_code == 201
        prov_bob = byok_env["captured_providers"][-1]
        assert prov_bob.api_key == bob_key

        # Confirm strict isolation
        assert prov_alice.api_key != prov_bob.api_key


@pytest.mark.asyncio
async def test_fallback_disabled_rejects_run_without_byok_credential(byok_env):
    """When allow_fallback is False, run without a tenant key fails with HTTP 400."""
    byok_env["settings"].allow_fallback_to_system_credentials = False
    app = byok_env["app"]
    alice_headers = {"Authorization": "Bearer token-alice"}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        sess_resp = await client.post(
            "/v1/sessions",
            headers=alice_headers,
            json={"title": "No BYOK Session"},
        )
        session_id = sess_resp.json()["id"]

        # Alice has no key registered for openrouter
        resp = await client.post(
            f"/v1/sessions/{session_id}/runs",
            headers=alice_headers,
            json={"prompt": "Should fail", "provider": "openrouter"},
        )
        assert resp.status_code == 400
        error_payload = resp.json()["error"]
        assert (
            "No tenant BYOK credential configured for provider 'openrouter'"
            in error_payload["message"]
        )

        # Now register key and retry
        await client.post(
            "/v1/vault/credentials",
            headers=alice_headers,
            json={"provider": "openrouter", "api_key": "sk-or-v1-now-registered-33333"},
        )
        retry_resp = await client.post(
            f"/v1/sessions/{session_id}/runs",
            headers=alice_headers,
            json={"prompt": "Now succeeds", "provider": "openrouter"},
        )
        assert retry_resp.status_code == 201
        assert retry_resp.json()["status"] == "succeeded"


@pytest.mark.asyncio
async def test_zero_leak_invariant_redacts_credentials_from_messages_and_errors(byok_env):
    """Verify that if upstream provider error contains the secret, it is strictly redacted."""
    app = byok_env["app"]
    alice_headers = {"Authorization": "Bearer token-alice"}
    secret_key = "sk-or-v1-leaky-credential-to-redact-99999"

    # Register leaky provider that raises an exception echoing the secret
    def _leaky_factory(api_key: str | None = None, **kw: Any) -> ModelProvider:
        return CapturingMockProvider(
            api_key=api_key,
            raise_on_complete=RuntimeError(
                f"Upstream provider failure with api key {api_key}: authentication rejected"
            ),
        )

    byok_env["provider_registry"].register("leaky", _leaky_factory, requires_credentials=True)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Save key in vault
        await client.post(
            "/v1/vault/credentials",
            headers=alice_headers,
            json={"provider": "leaky", "api_key": secret_key},
        )

        sess_resp = await client.post(
            "/v1/sessions",
            headers=alice_headers,
            json={"title": "Redaction Test Session"},
        )
        session_id = sess_resp.json()["id"]

        # 1. Test streaming error redaction
        async with client.stream(
            "POST",
            f"/v1/sessions/{session_id}/runs/stream",
            headers=alice_headers,
            json={"prompt": "Trigger leaky error", "provider": "leaky"},
        ) as stream_resp:
            assert stream_resp.status_code == 200
            raw_text = ""
            async for chunk in stream_resp.aiter_text():
                raw_text += chunk

        events = parse_sse_events(raw_text)
        failed_events = [e for e in events if e["event"] == "run_failed"]
        assert len(failed_events) == 1
        err_msg = failed_events[0]["data"]["error"]

        # Secret must be redacted in SSE payload
        assert secret_key not in err_msg
        assert "[REDACTED]" in err_msg
        assert secret_key not in raw_text

        # 2. Verify database message transcript and session messages never contain secret
        msg_resp = await client.get(
            f"/v1/sessions/{session_id}/messages",
            headers=alice_headers,
        )
        assert msg_resp.status_code == 200
        for msg in msg_resp.json():
            assert secret_key not in (msg.get("content") or "")

        # 3. Test one-shot run with leaky completion response text
        def _echo_secret_factory(api_key: str | None = None, **kw: Any) -> ModelProvider:
            return CapturingMockProvider(
                api_key=api_key,
                responses=[f"Your active key is {api_key}. Keep it safe."],
            )

        byok_env["provider_registry"].register(
            "echo", _echo_secret_factory, requires_credentials=True
        )

        await client.post(
            "/v1/vault/credentials",
            headers=alice_headers,
            json={"provider": "echo", "api_key": secret_key},
        )
        run_resp = await client.post(
            f"/v1/sessions/{session_id}/runs",
            headers=alice_headers,
            json={"prompt": "Echo key", "provider": "echo"},
        )
        assert run_resp.status_code == 201

        # Check messages in db: secret must be redacted
        msg_resp2 = await client.get(
            f"/v1/sessions/{session_id}/messages",
            headers=alice_headers,
        )
        all_contents = " ".join(m.get("content") or "" for m in msg_resp2.json())
        assert secret_key not in all_contents
        assert "[REDACTED]" in all_contents


@pytest.mark.asyncio
async def test_background_worker_byok_execution(byok_env):
    """Verify worker resolves and injects tenant BYOK vault keys during scheduled runs."""
    db_manager = byok_env["db_manager"]
    vault = byok_env["vault"]
    secret_key = "sk-worker-byok-key-77777"

    # Store credential for alice
    from icarus_core.persistence.repository import TenantCredentialRepository

    cred_repo = TenantCredentialRepository(db_manager, owner_id="alice", vault=vault)
    cred_repo.set_credential(provider="openrouter", secret=secret_key)

    # Enqueue a scheduled job for alice requesting openrouter
    job_repo = ScheduledJobRepository(db_manager)
    job = job_repo.create_job(
        ScheduledJobCreate(
            owner_id="alice",
            job_type="agent_run",
            scheduled_at=datetime.now(UTC),
            payload={
                "prompt": "Worker background query",
                "provider": "openrouter",
            },
        )
    )

    # Initialize worker daemon with provider registry and vault
    worker_settings = WorkerSettings(
        worker_id="test-worker-1",
        database_url="sqlite:///:memory:",
    )
    daemon = WorkerDaemon(
        settings=worker_settings,
        db_manager=db_manager,
        vault=vault,
        provider_registry=byok_env["provider_registry"],
    )

    # Process job once
    processed = await daemon.run_once()
    assert processed is not None
    assert processed.id == job.id

    # Verify provider was invoked with alice's decrypted secret key
    assert len(byok_env["captured_providers"]) >= 1
    worker_prov = byok_env["captured_providers"][-1]
    assert worker_prov.api_key == secret_key
