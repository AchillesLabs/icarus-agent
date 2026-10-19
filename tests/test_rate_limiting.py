"""Comprehensive test suite for sliding-window rate limiting and concurrency throttling.

Tests verify:
1. SlidingWindowRateLimiter algorithmic correctness, moving window eviction, burst handling,
   and deterministic time recovery using a virtualized clock (no flaky time.sleep).
2. Per-tenant overrides and concurrency acquisition/release scopes.
3. RateLimitMiddleware RFC 6585 compliance (X-RateLimit-* headers, Retry-After, HTTP 429).
4. Tenant isolation: tenant A hitting limits does not throttle tenant B.
5. IP throttling for unauthenticated requests and exemptions for health/docs/OPTIONS.
6. Execution concurrency limits on agent runs and recovery upon run completion.
"""

from __future__ import annotations

import asyncio
from typing import Annotated

import pytest
from fastapi import APIRouter, Depends
from httpx import ASGITransport, AsyncClient
from icarus_api import create_app
from icarus_api.auth import get_current_tenant
from icarus_api.config import ApiSettings
from icarus_api.run_registry import ActiveRunRegistry
from icarus_contracts import (
    RateLimitConfig,
    RateLimitStatus,
    SessionCreateRequest,
    TenantIdentity,
)
from icarus_core.persistence import Base, DatabaseManager
from icarus_core.providers import MockProvider, ProviderRegistry
from icarus_core.security import SlidingWindowRateLimiter


class VirtualClock:
    """Deterministic, virtualized clock for time-dependent rate limit tests without sleeping."""

    def __init__(self, start_time: float = 1000.0) -> None:
        self.current_time = start_time

    def time(self) -> float:
        return self.current_time

    def advance(self, seconds: float) -> None:
        self.current_time += seconds


# ============================================================================
# 1. SlidingWindowRateLimiter Unit Tests
# ============================================================================


def test_rate_limiter_initial_state_and_success():
    clock = VirtualClock(100.0)
    limiter = SlidingWindowRateLimiter(default_rpm=5, window_seconds=60.0, time_func=clock.time)

    res = limiter.check_rate_limit("tenant:alice")
    assert res.allowed is True
    assert res.limit == 5
    assert res.remaining == 4
    assert res.reset_seconds == 60
    assert res.retry_after == 0

    status = res.to_status()
    assert isinstance(status, RateLimitStatus)
    assert status.allowed is True
    assert status.remaining == 4


def test_rate_limiter_burst_and_exhaustion():
    clock = VirtualClock(100.0)
    limiter = SlidingWindowRateLimiter(default_rpm=3, window_seconds=60.0, time_func=clock.time)

    # First 3 requests succeed
    r1 = limiter.check_rate_limit("tenant:alice")
    r2 = limiter.check_rate_limit("tenant:alice")
    r3 = limiter.check_rate_limit("tenant:alice")

    assert r1.allowed and r1.remaining == 2
    assert r2.allowed and r2.remaining == 1
    assert r3.allowed and r3.remaining == 0

    # 4th request in the same window is rejected
    r4 = limiter.check_rate_limit("tenant:alice")
    assert r4.allowed is False
    assert r4.remaining == 0
    assert r4.limit == 3
    assert r4.retry_after == 60
    assert r4.reset_seconds == 60


def test_rate_limiter_sliding_window_recovery_with_virtual_clock():
    clock = VirtualClock(1000.0)
    limiter = SlidingWindowRateLimiter(default_rpm=2, window_seconds=60.0, time_func=clock.time)

    # Request at t = 1000.0
    r1 = limiter.check_rate_limit("tenant:alice")
    assert r1.allowed is True

    # Advance 20 seconds, request at t = 1020.0
    clock.advance(20.0)
    r2 = limiter.check_rate_limit("tenant:alice")
    assert r2.allowed is True

    # Limit reached at t = 1020.0 (2 in window)
    r3 = limiter.check_rate_limit("tenant:alice")
    assert r3.allowed is False
    # Oldest request was at 1000.0, so retry_after = ceil(1000 + 60 - 1020) = 40s
    assert r3.retry_after == 40

    # Advance 40.1s -> t = 1060.1 (t=1000.0 has expired, t=1020.0 remains)
    clock.advance(40.1)
    r4 = limiter.check_rate_limit("tenant:alice")
    assert r4.allowed is True
    assert r4.remaining == 0  # 1 from 1020.0 + 1 from 1060.1 = 2 used

    # Advance another 20s -> t = 1080.1 (t=1020.0 has expired)
    clock.advance(20.0)
    r5 = limiter.check_rate_limit("tenant:alice")
    assert r5.allowed is True


def test_rate_limiter_tenant_custom_rpm_overrides():
    clock = VirtualClock(100.0)
    limiter = SlidingWindowRateLimiter(
        default_rpm=2,
        tenant_rpm_limits={"tenant:vip": 10, "bob": 5},
        time_func=clock.time,
    )

    # Normal tenant has default limit 2
    assert limiter.get_rpm_limit("tenant:normal") == 2

    # VIP with prefix matches
    assert limiter.get_rpm_limit("tenant:vip") == 10

    # Bob specified without prefix matches both with and without prefix
    assert limiter.get_rpm_limit("bob") == 5
    assert limiter.get_rpm_limit("tenant:bob") == 5

    # Dynamic setter
    limiter.set_tenant_rpm_limit("tenant:normal", 50)
    assert limiter.get_rpm_limit("tenant:normal") == 50


def test_rate_limiter_reset_clears_records():
    clock = VirtualClock(100.0)
    limiter = SlidingWindowRateLimiter(default_rpm=1, time_func=clock.time)

    assert limiter.check_rate_limit("user-1").allowed is True
    assert limiter.check_rate_limit("user-1").allowed is False

    limiter.reset("user-1")
    assert limiter.check_rate_limit("user-1").allowed is True

    # Global reset
    limiter.check_rate_limit("user-2")
    limiter.reset()
    assert limiter.check_rate_limit("user-2").allowed is True


def test_rate_limiter_concurrency_tracking_and_scopes():
    limiter = SlidingWindowRateLimiter(
        max_concurrent_runs=2,
        tenant_concurrency_limits={"tenant:power": 5},
    )

    # Normal tenant limit 2
    assert limiter.get_active_concurrent_runs("tenant:normal") == 0
    assert limiter.acquire_concurrent_run("tenant:normal") is True
    assert limiter.acquire_concurrent_run("tenant:normal") is True
    # Ceiling reached
    assert limiter.acquire_concurrent_run("tenant:normal") is False
    assert limiter.get_active_concurrent_runs("tenant:normal") == 2

    limiter.release_concurrent_run("tenant:normal")
    assert limiter.get_active_concurrent_runs("tenant:normal") == 1
    assert limiter.acquire_concurrent_run("tenant:normal") is True

    # VIP tenant limit 5
    assert limiter.get_concurrency_limit("tenant:power") == 5
    for _ in range(5):
        assert limiter.acquire_concurrent_run("tenant:power") is True
    assert limiter.acquire_concurrent_run("tenant:power") is False

    # Dynamic concurrency setter
    limiter.set_tenant_concurrency_limit("tenant:power", 10)
    assert limiter.get_concurrency_limit("tenant:power") == 10


def test_rate_limiter_concurrency_context_manager():
    limiter = SlidingWindowRateLimiter(max_concurrent_runs=1)

    with limiter.concurrency_scope("tenant:alice") as acquired1:
        assert acquired1 is True
        assert limiter.get_active_concurrent_runs("tenant:alice") == 1

        with limiter.concurrency_scope("tenant:alice") as acquired2:
            assert acquired2 is False
            assert limiter.get_active_concurrent_runs("tenant:alice") == 1

    assert limiter.get_active_concurrent_runs("tenant:alice") == 0


@pytest.mark.asyncio
async def test_rate_limiter_async_concurrency_context_manager():
    limiter = SlidingWindowRateLimiter(max_concurrent_runs=1)

    async with limiter.async_concurrency_scope("tenant:bob") as acquired1:
        assert acquired1 is True
        assert limiter.get_active_concurrent_runs("tenant:bob") == 1

        async with limiter.async_concurrency_scope("tenant:bob") as acquired2:
            assert acquired2 is False

    assert limiter.get_active_concurrent_runs("tenant:bob") == 0


def test_contracts_rate_limit_config_validation():
    cfg = RateLimitConfig(default_rpm=100, window_seconds=30.0, max_concurrent_runs=10)
    assert cfg.enabled is True
    assert cfg.default_rpm == 100
    assert cfg.window_seconds == 30.0
    assert cfg.max_concurrent_runs == 10


# ============================================================================
# 2. RateLimitMiddleware Integration Tests
# ============================================================================


@pytest.mark.asyncio
async def test_middleware_injects_rfc6585_headers_on_success():
    clock = VirtualClock(100.0)
    limiter = SlidingWindowRateLimiter(default_rpm=10, window_seconds=60.0, time_func=clock.time)
    settings = ApiSettings(auth_tokens={"alice-key": "alice"})
    app = create_app(settings=settings, rate_limiter=limiter)

    router = APIRouter()

    @router.get("/test-endpoint")
    async def test_endpoint():
        return {"status": "ok"}

    app.include_router(router)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/test-endpoint", headers={"Authorization": "Bearer alice-key"})
        assert resp.status_code == 200
        assert resp.headers["X-RateLimit-Limit"] == "10"
        assert resp.headers["X-RateLimit-Remaining"] == "9"
        assert int(resp.headers["X-RateLimit-Reset"]) > 0


@pytest.mark.asyncio
async def test_middleware_flooding_returns_http_429_with_retry_after():
    clock = VirtualClock(500.0)
    limiter = SlidingWindowRateLimiter(default_rpm=2, window_seconds=60.0, time_func=clock.time)
    settings = ApiSettings(auth_tokens={"alice-key": "alice"})
    app = create_app(settings=settings, rate_limiter=limiter)

    router = APIRouter()

    @router.get("/resource")
    async def get_resource():
        return {"data": "val"}

    app.include_router(router)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        headers = {"Authorization": "Bearer alice-key"}

        r1 = await client.get("/resource", headers=headers)
        assert r1.status_code == 200
        assert r1.headers["X-RateLimit-Remaining"] == "1"

        r2 = await client.get("/resource", headers=headers)
        assert r2.status_code == 200
        assert r2.headers["X-RateLimit-Remaining"] == "0"

        # 3rd request exceeds limit
        r3 = await client.get("/resource", headers=headers)
        assert r3.status_code == 429
        assert "Retry-After" in r3.headers
        assert r3.headers["Retry-After"] == "60"
        assert r3.headers["X-RateLimit-Remaining"] == "0"
        assert r3.headers["X-RateLimit-Limit"] == "2"

        body = r3.json()
        assert body["error"]["code"] == "rate_limited"
        assert "Rate limit exceeded" in body["error"]["message"]
        assert body["error"]["details"]["retry_after"] == 60


@pytest.mark.asyncio
async def test_middleware_recovers_after_virtual_time_advances():
    clock = VirtualClock(100.0)
    limiter = SlidingWindowRateLimiter(default_rpm=1, window_seconds=60.0, time_func=clock.time)
    settings = ApiSettings(auth_tokens={"alice-key": "alice"})
    app = create_app(settings=settings, rate_limiter=limiter)

    router = APIRouter()

    @router.get("/ping")
    async def ping():
        return {"ping": "pong"}

    app.include_router(router)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        headers = {"Authorization": "Bearer alice-key"}

        # Request 1 succeeds
        r1 = await client.get("/ping", headers=headers)
        assert r1.status_code == 200

        # Request 2 is throttled
        r2 = await client.get("/ping", headers=headers)
        assert r2.status_code == 429

        # Advance virtual clock by 61 seconds (window reset)
        clock.advance(61.0)

        # Request 3 succeeds again!
        r3 = await client.get("/ping", headers=headers)
        assert r3.status_code == 200
        assert r3.headers["X-RateLimit-Remaining"] == "0"


@pytest.mark.asyncio
async def test_middleware_tenant_isolation_under_flooding():
    """Ensure Tenant A being throttled does not affect Tenant B."""
    clock = VirtualClock(100.0)
    limiter = SlidingWindowRateLimiter(default_rpm=1, window_seconds=60.0, time_func=clock.time)
    settings = ApiSettings(
        auth_tokens={
            "alice-key": "alice",
            "bob-key": "bob",
        }
    )
    app = create_app(settings=settings, rate_limiter=limiter)

    router = APIRouter()

    @router.get("/status")
    async def get_status(tenant: Annotated[TenantIdentity, Depends(get_current_tenant)]):
        return {"tenant": tenant.owner_id}

    app.include_router(router)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        alice_headers = {"Authorization": "Bearer alice-key"}
        bob_headers = {"Authorization": "Bearer bob-key"}

        # Alice consumes quota
        r_a1 = await client.get("/status", headers=alice_headers)
        assert r_a1.status_code == 200

        # Alice is throttled
        r_a2 = await client.get("/status", headers=alice_headers)
        assert r_a2.status_code == 429

        # Bob is NOT throttled
        r_b1 = await client.get("/status", headers=bob_headers)
        assert r_b1.status_code == 200
        assert r_b1.json()["tenant"] == "bob"


@pytest.mark.asyncio
async def test_middleware_ip_fallback_for_unauthenticated_requests():
    """Unauthenticated requests are tracked and throttled by IP."""
    clock = VirtualClock(100.0)
    limiter = SlidingWindowRateLimiter(default_rpm=2, window_seconds=60.0, time_func=clock.time)
    app = create_app(rate_limiter=limiter)

    router = APIRouter()

    @router.get("/public")
    async def public_endpoint():
        return {"public": True}

    app.include_router(router)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r1 = await client.get("/public")
        assert r1.status_code == 200

        r2 = await client.get("/public")
        assert r2.status_code == 200

        r3 = await client.get("/public")
        assert r3.status_code == 429
        assert r3.json()["error"]["code"] == "rate_limited"


@pytest.mark.asyncio
async def test_middleware_exempt_paths_and_cors_options():
    """Health probes, OpenAPI docs, and CORS OPTIONS are exempt from rate limits."""
    limiter = SlidingWindowRateLimiter(default_rpm=1)
    app = create_app(rate_limiter=limiter)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Multiple health requests succeed despite limit=1
        for _ in range(5):
            resp = await client.get("/health")
            assert resp.status_code == 200
            assert "X-RateLimit-Limit" not in resp.headers

        # Docs are exempt
        docs_resp = await client.get("/docs")
        assert docs_resp.status_code == 200
        assert "X-RateLimit-Limit" not in docs_resp.headers

        # OPTIONS preflight is exempt
        options_resp = await client.options("/v1/sessions")
        assert "X-RateLimit-Limit" not in options_resp.headers


@pytest.mark.asyncio
async def test_middleware_disabled_via_settings():
    settings = ApiSettings(rate_limit_enabled=False)
    limiter = SlidingWindowRateLimiter(default_rpm=1)
    app = create_app(settings=settings, rate_limiter=limiter)

    router = APIRouter()

    @router.get("/unmetered")
    async def unmetered():
        return {"ok": True}

    app.include_router(router)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        for _ in range(5):
            resp = await client.get("/unmetered")
            assert resp.status_code == 200
            assert "X-RateLimit-Limit" not in resp.headers


# ============================================================================
# 3. Execution Concurrency Throttling Tests
# ============================================================================


@pytest.mark.asyncio
async def test_concurrency_ceiling_enforced_on_agent_runs():
    """Verify that exceeding max_concurrent_runs_per_tenant returns HTTP 429 with Retry-After."""
    db_manager = DatabaseManager(db_url="sqlite:///:memory:")
    Base.metadata.create_all(db_manager.engine)

    provider_registry = ProviderRegistry()
    mock_provider = MockProvider(responses=["Hello world"])
    provider_registry.register("mock", lambda **kw: mock_provider, requires_credentials=False)

    settings = ApiSettings(
        auth_tokens={"alice-key": "alice"},
        max_concurrent_runs_per_tenant=1,
    )
    limiter = SlidingWindowRateLimiter(max_concurrent_runs=1)
    run_registry = ActiveRunRegistry()

    app = create_app(
        settings=settings,
        db_manager=db_manager,
        provider_registry=provider_registry,
        run_registry=run_registry,
        rate_limiter=limiter,
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        headers = {"Authorization": "Bearer alice-key"}

        # Create session
        s_resp = await client.post(
            "/v1/sessions",
            json=SessionCreateRequest(title="Concurrency Test").model_dump(),
            headers=headers,
        )
        assert s_resp.status_code == 201
        session_id = s_resp.json()["id"]

        # Simulate an ongoing active run in run_registry
        async def dummy_slow_task():
            await asyncio.sleep(10)

        task = asyncio.create_task(dummy_slow_task())
        await run_registry.register("run-active-1", owner_id="alice", task=task)

        try:
            # Attempt to trigger a second run while one is already active (limit = 1)
            run_resp = await client.post(
                f"/v1/sessions/{session_id}/runs",
                json={"prompt": "Do work"},
                headers=headers,
            )
            assert run_resp.status_code == 429
            assert "Retry-After" in run_resp.headers
            assert "concurrency limit reached" in run_resp.json()["error"]["message"].lower()

            # Attempt stream run as well
            stream_resp = await client.post(
                f"/v1/sessions/{session_id}/runs/stream",
                json={"prompt": "Do stream work"},
                headers=headers,
            )
            assert stream_resp.status_code == 429
            assert "Retry-After" in stream_resp.headers
            assert "concurrency limit reached" in stream_resp.json()["error"]["message"].lower()

        finally:
            task.cancel()
            await run_registry.unregister("run-active-1")


@pytest.mark.asyncio
async def test_concurrency_recovery_after_run_completion():
    """Verify that when an active run completes, the concurrency slot is released."""
    db_manager = DatabaseManager(db_url="sqlite:///:memory:")
    Base.metadata.create_all(db_manager.engine)

    provider_registry = ProviderRegistry()
    mock_provider = MockProvider(responses=["Completed response 1", "Completed response 2"])
    provider_registry.register("mock", lambda **kw: mock_provider, requires_credentials=False)

    settings = ApiSettings(
        auth_tokens={"alice-key": "alice"},
        max_concurrent_runs_per_tenant=1,
    )
    limiter = SlidingWindowRateLimiter(max_concurrent_runs=1)
    run_registry = ActiveRunRegistry()

    app = create_app(
        settings=settings,
        db_manager=db_manager,
        provider_registry=provider_registry,
        run_registry=run_registry,
        rate_limiter=limiter,
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        headers = {"Authorization": "Bearer alice-key"}

        s_resp = await client.post(
            "/v1/sessions",
            json=SessionCreateRequest(title="Concurrency Recovery").model_dump(),
            headers=headers,
        )
        session_id = s_resp.json()["id"]

        # Run 1 executes synchronously and completes
        r1 = await client.post(
            f"/v1/sessions/{session_id}/runs",
            json={"prompt": "First prompt"},
            headers=headers,
        )
        assert r1.status_code == 201
        assert r1.json()["status"] == "succeeded"

        # Concurrency slot is freed, so Run 2 succeeds immediately
        r2 = await client.post(
            f"/v1/sessions/{session_id}/runs",
            json={"prompt": "Second prompt"},
            headers=headers,
        )
        assert r2.status_code == 201
        assert r2.json()["status"] == "succeeded"
