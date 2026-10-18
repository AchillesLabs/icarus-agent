"""Tests for API authentication, token validation, and tenant identity resolution."""

import pytest
from icarus_api.auth import resolve_tenant_identity
from icarus_api.config import ApiSettings
from icarus_contracts import TenantIdentity


def test_resolve_tenant_identity_with_single_auth_token():
    settings = ApiSettings(auth_token="master-secret", default_owner_id="default-tenant")

    identity = resolve_tenant_identity("master-secret", settings)
    assert identity is not None
    assert identity.owner_id == "default-tenant"
    assert identity.token == "master-secret"

    invalid = resolve_tenant_identity("wrong-secret", settings)
    assert invalid is None


def test_resolve_tenant_identity_with_auth_tokens_mapping():
    settings = ApiSettings(auth_tokens={"alice-secret": "tenant-alice", "bob-secret": "tenant-bob"})

    id_alice = resolve_tenant_identity("alice-secret", settings)
    assert id_alice is not None
    assert id_alice.owner_id == "tenant-alice"

    id_bob = resolve_tenant_identity("bob-secret", settings)
    assert id_bob is not None
    assert id_bob.owner_id == "tenant-bob"

    id_eve = resolve_tenant_identity("eve-secret", settings)
    assert id_eve is None


def test_resolve_tenant_identity_with_scoped_token_prefix():
    settings = ApiSettings(auth_token="service-secret")

    scoped = resolve_tenant_identity("tenant-custom:service-secret", settings)
    assert scoped is not None
    assert scoped.owner_id == "tenant-custom"

    bad_scoped = resolve_tenant_identity("tenant-custom:wrong-secret", settings)
    assert bad_scoped is None


def test_resolve_tenant_identity_with_no_configured_secrets():
    settings = ApiSettings()

    assert resolve_tenant_identity("any-token", settings) is None


def test_api_settings_parses_auth_tokens_string():
    settings_json = ApiSettings(auth_tokens='{"tok-1": "owner-1", "tok-2": "owner-2"}')  # type: ignore[arg-type]
    assert settings_json.auth_tokens == {"tok-1": "owner-1", "tok-2": "owner-2"}

    settings_delim = ApiSettings(auth_tokens="tok-a:owner-a,tok-b:owner-b")  # type: ignore[arg-type]
    assert settings_delim.auth_tokens == {"tok-a": "owner-a", "tok-b": "owner-b"}


@pytest.mark.asyncio
async def test_protected_route_unauthenticated_returns_401():
    from typing import Annotated

    from fastapi import APIRouter, Depends
    from httpx import ASGITransport, AsyncClient
    from icarus_api import create_app
    from icarus_api.auth import get_current_tenant

    settings = ApiSettings(auth_token="secret-123")
    app = create_app(settings=settings)
    router = APIRouter()

    @router.get("/protected")
    async def protected_endpoint(
        tenant: Annotated[TenantIdentity, Depends(get_current_tenant)],
    ) -> dict[str, str]:
        return {"owner_id": tenant.owner_id}

    app.include_router(router)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/protected")
        assert resp.status_code == 401
        data = resp.json()
        assert data["error"]["code"] == "unauthorized"
        assert "credentials" in data["error"]["message"].lower()
        assert resp.headers.get("www-authenticate") == "Bearer"


@pytest.mark.asyncio
async def test_protected_route_invalid_token_returns_401():
    from typing import Annotated

    from fastapi import APIRouter, Depends
    from httpx import ASGITransport, AsyncClient
    from icarus_api import create_app
    from icarus_api.auth import get_current_tenant

    settings = ApiSettings(auth_token="secret-123")
    app = create_app(settings=settings)
    router = APIRouter()

    @router.get("/protected")
    async def protected_endpoint(
        tenant: Annotated[TenantIdentity, Depends(get_current_tenant)],
    ) -> dict[str, str]:
        return {"owner_id": tenant.owner_id}

    app.include_router(router)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/protected", headers={"Authorization": "Bearer wrong-token"})
        assert resp.status_code == 401
        data = resp.json()
        assert data["error"]["code"] == "unauthorized"
        assert resp.headers.get("www-authenticate") == "Bearer"


@pytest.mark.asyncio
async def test_protected_route_valid_bearer_token_succeeds_and_binds_state():
    from typing import Annotated

    from fastapi import APIRouter, Depends, Request
    from httpx import ASGITransport, AsyncClient
    from icarus_api import create_app
    from icarus_api.auth import get_current_tenant, get_tenant_owner_id

    settings = ApiSettings(auth_tokens={"alice-key": "alice"})
    app = create_app(settings=settings)
    router = APIRouter()

    @router.get("/protected")
    async def protected_endpoint(
        request: Request,
        tenant: Annotated[TenantIdentity, Depends(get_current_tenant)],
        owner_id: Annotated[str, Depends(get_tenant_owner_id)],
    ) -> dict[str, str]:
        assert request.state.identity.owner_id == "alice"
        assert request.state.owner_id == "alice"
        return {"tenant": tenant.owner_id, "owner_id": owner_id}

    app.include_router(router)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/protected", headers={"Authorization": "Bearer alice-key"})
        assert resp.status_code == 200
        assert resp.json() == {"tenant": "alice", "owner_id": "alice"}


@pytest.mark.asyncio
async def test_protected_route_valid_api_key_header_succeeds():
    from typing import Annotated

    from fastapi import APIRouter, Depends
    from httpx import ASGITransport, AsyncClient
    from icarus_api import create_app
    from icarus_api.auth import get_current_tenant

    settings = ApiSettings(auth_tokens={"bob-api-key": "bob"})
    app = create_app(settings=settings)
    router = APIRouter()

    @router.get("/protected")
    async def protected_endpoint(
        tenant: Annotated[TenantIdentity, Depends(get_current_tenant)],
    ) -> dict[str, str]:
        return {"tenant": tenant.owner_id}

    app.include_router(router)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/protected", headers={"X-API-Key": "bob-api-key"})
        assert resp.status_code == 200
        assert resp.json() == {"tenant": "bob"}
