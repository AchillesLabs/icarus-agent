"""Comprehensive unit and integration tests for dynamic API token issuance,

constant-time verification, in-memory caching, and instant revocation.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from icarus_api.app import create_app
from icarus_api.auth import TokenValidationCache, resolve_tenant_identity
from icarus_api.config import ApiSettings
from icarus_contracts.tokens import ApiTokenResponse
from icarus_core.persistence.database import DatabaseManager
from icarus_core.persistence.models import Base
from icarus_core.persistence.repository import ApiTokenRepository, TenantApiTokenRepository
from icarus_core.security import generate_api_token, verify_token_hash


@pytest.fixture
def test_db_manager() -> DatabaseManager:
    """Provide a fresh in-memory SQLite database initialized with all tables."""
    db_manager = DatabaseManager(db_url="sqlite:///:memory:")
    Base.metadata.create_all(db_manager.engine)
    return db_manager


def test_generate_api_token_and_constant_time_verification():
    raw_token, prefix, token_hash = generate_api_token()

    assert raw_token.startswith("sk_icarus_")
    assert len(raw_token) > 40
    assert len(token_hash) == 64
    assert prefix.startswith("sk_icarus_")
    assert prefix.endswith(raw_token[-4:])
    assert "..." in prefix

    # Constant time verification
    assert verify_token_hash(raw_token, token_hash) is True
    assert verify_token_hash(raw_token + "tampered", token_hash) is False
    assert verify_token_hash("sk_icarus_wrong", token_hash) is False


def test_token_validation_cache_lifecycle():
    cache = TokenValidationCache(ttl_seconds=0.5)

    token_hash = "testhash123"
    token_id = "token-uuid-1"
    owner_id = "tenant-alpha"

    # Set and get
    cache.set(token_hash=token_hash, token_id=token_id, owner_id=owner_id)
    cached = cache.get(token_hash)
    assert cached is not None
    assert cached.owner_id == owner_id
    assert cached.token_id == token_id

    # Invalidate by token_id
    assert cache.invalidate_by_token_id(token_id) is True
    assert cache.get(token_hash) is None

    # Invalidate by token_hash
    cache.set(token_hash=token_hash, token_id=token_id, owner_id=owner_id)
    assert cache.invalidate_by_token_hash(token_hash) is True
    assert cache.get(token_hash) is None

    # TTL eviction
    cache.set(token_hash=token_hash, token_id=token_id, owner_id=owner_id)
    time.sleep(0.6)
    assert cache.get(token_hash) is None

    # Expired token in cache
    past_exp = datetime.now(UTC) - timedelta(minutes=1)
    cache.set(token_hash="expiredhash", token_id="t-exp", owner_id=owner_id, expires_at=past_exp)
    assert cache.get("expiredhash") is None


def test_api_token_repository_crud(test_db_manager: DatabaseManager):
    repo = ApiTokenRepository(test_db_manager)
    tenant_repo = TenantApiTokenRepository(test_db_manager, owner_id="tenant-1")

    raw_token, prefix, token_hash = generate_api_token()

    # Create token
    created = tenant_repo.create_token(
        name="MacBook CLI",
        token_hash=token_hash,
        prefix=prefix,
    )
    assert isinstance(created, ApiTokenResponse)
    assert created.name == "MacBook CLI"
    assert created.owner_id == "tenant-1"
    assert created.prefix == prefix
    assert created.is_active is True
    assert created.revoked_at is None
    assert created.last_used_at is None

    # Lookup by hash
    by_hash = repo.get_token_by_hash(token_hash)
    assert by_hash is not None
    assert by_hash.id == created.id

    # Touch last used
    now = datetime.now(UTC)
    repo.touch_last_used(created.id, now=now)
    touched = tenant_repo.get_token(created.id)
    assert touched is not None
    assert touched.last_used_at is not None

    # List tokens
    tokens = tenant_repo.list_tokens(include_revoked=True)
    assert len(tokens) == 1
    assert tokens[0].id == created.id

    # Revoke token
    revoked = tenant_repo.revoke_token(created.id)
    assert revoked is not None
    assert revoked.revoked_at is not None
    assert revoked.is_active is False

    # List without revoked
    active_tokens = tenant_repo.list_tokens(include_revoked=False)
    assert len(active_tokens) == 0


def test_resolve_tenant_identity_with_dynamic_tokens(test_db_manager: DatabaseManager):
    settings = ApiSettings()
    cache = TokenValidationCache()
    repo = ApiTokenRepository(test_db_manager)

    raw_token, prefix, token_hash = generate_api_token()
    token = repo.create_token(
        owner_id="tenant-dynamic",
        name="Dynamic Key",
        token_hash=token_hash,
        prefix=prefix,
    )

    # First resolve: misses cache, queries DB, populates cache
    identity = resolve_tenant_identity(
        token=raw_token,
        settings=settings,
        db_manager=test_db_manager,
        token_cache=cache,
    )
    assert identity is not None
    assert identity.owner_id == "tenant-dynamic"
    assert identity.token == raw_token

    # Cache should now have the token
    cached = cache.get(token_hash)
    assert cached is not None
    assert cached.owner_id == "tenant-dynamic"

    # Second resolve: hits cache
    cached_identity = resolve_tenant_identity(
        token=raw_token,
        settings=settings,
        db_manager=test_db_manager,
        token_cache=cache,
    )
    assert cached_identity is not None
    assert cached_identity.owner_id == "tenant-dynamic"

    # Revoke token and clear cache
    repo.revoke_token(token.id)
    cache.invalidate_by_token_id(token.id)

    # Resolve after revocation must return None
    assert (
        resolve_tenant_identity(
            token=raw_token,
            settings=settings,
            db_manager=test_db_manager,
            token_cache=cache,
        )
        is None
    )


@pytest.mark.asyncio
async def test_api_issue_token_and_authenticate_lifecycle(test_db_manager: DatabaseManager):
    settings = ApiSettings(auth_tokens={"bootstrap-admin": "admin-org"})
    cache = TokenValidationCache()
    app = create_app(settings=settings, db_manager=test_db_manager, token_cache=cache)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Issue a new dynamic API token
        issue_resp = await client.post(
            "/v1/auth/tokens",
            json={"name": "Dev Workstation"},
            headers={"Authorization": "Bearer bootstrap-admin"},
        )
        assert issue_resp.status_code == 201
        data = issue_resp.json()
        assert "token" in data
        assert data["token"].startswith("sk_icarus_")
        assert data["name"] == "Dev Workstation"
        assert data["owner_id"] == "admin-org"
        assert data["is_active"] is True
        token_id = data["id"]
        raw_secret = data["token"]

        # 2. Authenticate to protected API using newly issued dynamic token
        list_resp = await client.get(
            "/v1/auth/tokens",
            headers={"Authorization": f"Bearer {raw_secret}"},
        )
        assert list_resp.status_code == 200
        tokens_list = list_resp.json()
        assert len(tokens_list) == 1
        assert tokens_list[0]["id"] == token_id
        assert tokens_list[0]["name"] == "Dev Workstation"
        # Verify raw secret is NOT leaked in list response
        assert "token" not in tokens_list[0]

        # 3. Access another protected resource (sessions) with the dynamic token
        session_resp = await client.post(
            "/v1/sessions",
            json={"title": "Token Authenticated Session"},
            headers={"Authorization": f"Bearer {raw_secret}"},
        )
        assert session_resp.status_code == 201
        session_data = session_resp.json()
        assert session_data["owner_id"] == "admin-org"

        # 4. Revoke the token
        revoke_resp = await client.post(
            f"/v1/auth/tokens/{token_id}/revoke",
            headers={"Authorization": "Bearer bootstrap-admin"},
        )
        assert revoke_resp.status_code == 200
        revoked_data = revoke_resp.json()
        assert revoked_data["id"] == token_id
        assert revoked_data["revoked_at"] is not None
        assert revoked_data["is_active"] is False

        # 5. Verify the revoked token is immediately rejected with HTTP 401
        rejected_resp = await client.get(
            "/v1/auth/tokens",
            headers={"Authorization": f"Bearer {raw_secret}"},
        )
        assert rejected_resp.status_code == 401
        err_data = rejected_resp.json()
        assert err_data["error"]["code"] == "unauthorized"


@pytest.mark.asyncio
async def test_api_expired_token_rejected_immediately(test_db_manager: DatabaseManager):
    settings = ApiSettings(auth_tokens={"root-key": "test-tenant"})
    cache = TokenValidationCache()
    app = create_app(settings=settings, db_manager=test_db_manager, token_cache=cache)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Create a token that already expired 10 minutes ago
        past_expiration = (datetime.now(UTC) - timedelta(minutes=10)).isoformat()
        issue_resp = await client.post(
            "/v1/auth/tokens",
            json={"name": "Expired Token", "expires_at": past_expiration},
            headers={"Authorization": "Bearer root-key"},
        )
        assert issue_resp.status_code == 201
        raw_secret = issue_resp.json()["token"]

        # Attempt to authenticate with expired token
        resp = await client.get(
            "/v1/auth/tokens",
            headers={"Authorization": f"Bearer {raw_secret}"},
        )
        assert resp.status_code == 401
        assert resp.json()["error"]["code"] == "unauthorized"


@pytest.mark.asyncio
async def test_cross_tenant_token_isolation(test_db_manager: DatabaseManager):
    settings = ApiSettings(
        auth_tokens={
            "alice-bootstrap": "tenant-alice",
            "bob-bootstrap": "tenant-bob",
        }
    )
    cache = TokenValidationCache()
    app = create_app(settings=settings, db_manager=test_db_manager, token_cache=cache)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Alice creates a token
        alice_create = await client.post(
            "/v1/auth/tokens",
            json={"name": "Alice Laptop"},
            headers={"Authorization": "Bearer alice-bootstrap"},
        )
        assert alice_create.status_code == 201
        alice_token_id = alice_create.json()["id"]
        alice_token_secret = alice_create.json()["token"]

        # Bob creates a token
        bob_create = await client.post(
            "/v1/auth/tokens",
            json={"name": "Bob Server"},
            headers={"Authorization": "Bearer bob-bootstrap"},
        )
        assert bob_create.status_code == 201
        bob_token_id = bob_create.json()["id"]

        # Bob lists tokens: must NOT see Alice's token
        bob_list = await client.get(
            "/v1/auth/tokens",
            headers={"Authorization": "Bearer bob-bootstrap"},
        )
        assert bob_list.status_code == 200
        bob_tokens = bob_list.json()
        assert len(bob_tokens) == 1
        assert bob_tokens[0]["id"] == bob_token_id
        assert all(t["id"] != alice_token_id for t in bob_tokens)

        # Bob attempts to revoke Alice's token: must return 404
        bob_revoke_alice = await client.post(
            f"/v1/auth/tokens/{alice_token_id}/revoke",
            headers={"Authorization": "Bearer bob-bootstrap"},
        )
        assert bob_revoke_alice.status_code == 404

        # Alice's token still works for Alice
        alice_check = await client.get(
            "/v1/auth/tokens",
            headers={"Authorization": f"Bearer {alice_token_secret}"},
        )
        assert alice_check.status_code == 200
        assert alice_check.json()[0]["owner_id"] == "tenant-alice"
