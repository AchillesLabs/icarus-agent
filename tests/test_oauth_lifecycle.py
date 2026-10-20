"""Comprehensive end-to-end unit and integration tests for OAuth 2.0 PKCE lifecycle and app connections."""

from __future__ import annotations

import base64
import hashlib
import urllib.parse
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import httpx
import pytest
from fastapi.testclient import TestClient
from icarus_api.app import create_app
from icarus_contracts.integrations import (
    ConnectionStatus,
)
from icarus_core.integrations.google import (
    DEFAULT_GOOGLE_SCOPES,
    GOOGLE_AUTH_URL,
    GOOGLE_REVOKE_URL,
    GOOGLE_TOKEN_URL,
    GoogleOAuthClient,
)
from icarus_core.integrations.loopback import LoopbackCallbackServer
from icarus_core.integrations.pkce import (
    generate_code_challenge,
    generate_code_verifier,
    generate_oauth_state,
)
from icarus_core.persistence.database import DatabaseManager
from icarus_core.persistence.repository import (
    IntegrationRepository,
    TenantIntegrationRepository,
)
from icarus_core.security.vault import CredentialVault

# ---------------------------------------------------------------------------
# 1. PKCE and Security Primitives Tests
# ---------------------------------------------------------------------------


def test_pkce_generation() -> None:
    verifier = generate_code_verifier(64)
    assert len(verifier) == 64
    assert verifier.isalnum() or any(c in "-._~" for c in verifier)

    challenge = generate_code_challenge(verifier)
    assert len(challenge) > 20
    assert "=" not in challenge  # base64url unpadded

    # Manual verification of SHA-256 challenge calculation
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    expected = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    assert challenge == expected


def test_state_token_uniqueness() -> None:
    s1 = generate_oauth_state()
    s2 = generate_oauth_state()
    assert s1 != s2
    assert len(s1) >= 32


# ---------------------------------------------------------------------------
# 2. GoogleOAuthClient Tests
# ---------------------------------------------------------------------------


def test_google_oauth_client_authorization_flow() -> None:
    client = GoogleOAuthClient(client_id="test-client-id-123.apps.googleusercontent.com")
    auth_url, state, verifier = client.create_authorization_flow(
        redirect_uri="http://127.0.0.1:8080/callback",
        scopes=DEFAULT_GOOGLE_SCOPES,
    )

    assert auth_url.startswith(GOOGLE_AUTH_URL)
    parsed = urllib.parse.urlparse(auth_url)
    params = urllib.parse.parse_qs(parsed.query)

    assert params["client_id"][0] == "test-client-id-123.apps.googleusercontent.com"
    assert params["redirect_uri"][0] == "http://127.0.0.1:8080/callback"
    assert params["response_type"][0] == "code"
    assert params["code_challenge_method"][0] == "S256"
    assert params["state"][0] == state
    assert params["code_challenge"][0] == generate_code_challenge(verifier)


def test_google_oauth_client_exchange_code(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == GOOGLE_TOKEN_URL
        content = request.read().decode("utf-8")
        assert "grant_type=authorization_code" in content
        assert "code=auth_code_xyz" in content
        assert "code_verifier=verifier_abc" in content
        return httpx.Response(
            200,
            json={
                "access_token": "ya29.mock_access_token",
                "refresh_token": "1//mock_refresh_token",
                "expires_in": 3600,
                "token_type": "Bearer",
                "scope": "https://www.googleapis.com/auth/calendar.readonly",
            },
        )

    mock_http = httpx.Client(transport=httpx.MockTransport(handler))
    client = GoogleOAuthClient(
        client_id="test-id",
        client_secret="test-secret",
        http_client=mock_http,
    )

    tokens = client.exchange_code(
        code="auth_code_xyz",
        redirect_uri="http://127.0.0.1:8080/callback",
        code_verifier="verifier_abc",
    )
    assert tokens["access_token"] == "ya29.mock_access_token"
    assert tokens["refresh_token"] == "1//mock_refresh_token"


def test_google_oauth_client_refresh_token() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == GOOGLE_TOKEN_URL
        content = request.read().decode("utf-8")
        assert "grant_type=refresh_token" in content
        assert "refresh_token=old_refresh_123" in content
        return httpx.Response(
            200,
            json={
                "access_token": "ya29.new_access_token",
                "expires_in": 3600,
                "token_type": "Bearer",
            },
        )

    mock_http = httpx.Client(transport=httpx.MockTransport(handler))
    client = GoogleOAuthClient(client_id="test-id", http_client=mock_http)
    tokens = client.refresh_access_token("old_refresh_123")
    assert tokens["access_token"] == "ya29.new_access_token"


def test_google_oauth_client_revocation() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert GOOGLE_REVOKE_URL in str(request.url)
        return httpx.Response(200, json={})

    mock_http = httpx.Client(transport=httpx.MockTransport(handler))
    client = GoogleOAuthClient(client_id="test-id", http_client=mock_http)
    assert client.revoke_token("token_to_revoke") is True


# ---------------------------------------------------------------------------
# 3. Ephemeral Loopback Server Tests
# ---------------------------------------------------------------------------


def test_loopback_server_success() -> None:
    server = LoopbackCallbackServer(expected_state="valid_state_123", timeout=5.0)
    redirect_uri = server.start()
    try:
        assert redirect_uri.startswith("http://127.0.0.1:")
        assert redirect_uri.endswith("/callback")

        # Simulate browser redirect
        resp = httpx.get(
            f"{redirect_uri}?state=valid_state_123&code=secret_oauth_code_456",
            timeout=2.0,
        )
        assert resp.status_code == 200
        assert "Authorization Complete" in resp.text

        code = server.wait_for_code()
        assert code == "secret_oauth_code_456"
    finally:
        server.shutdown()


def test_loopback_server_state_mismatch_rejection() -> None:
    server = LoopbackCallbackServer(expected_state="valid_state_123", timeout=5.0)
    redirect_uri = server.start()
    try:
        # Simulate CSRF attempt with tampered state
        resp = httpx.get(
            f"{redirect_uri}?state=attacker_state&code=malicious_code",
            timeout=2.0,
        )
        assert resp.status_code == 403
        assert "state mismatch" in resp.text.lower()

        with pytest.raises(ValueError, match="state mismatch"):
            server.wait_for_code()
    finally:
        server.shutdown()


# ---------------------------------------------------------------------------
# 4. Persistence, Encryption at Rest & Tenant Isolation Tests
# ---------------------------------------------------------------------------


@pytest.fixture
def sqlite_db_manager() -> DatabaseManager:
    from icarus_core.persistence.models import Base

    mgr = DatabaseManager("sqlite:///:memory:")
    Base.metadata.create_all(mgr.engine)
    return mgr


def test_integration_repository_encryption_and_tenant_isolation(
    sqlite_db_manager: DatabaseManager,
) -> None:
    vault = CredentialVault(allow_insecure_dev_key=True)
    repo = IntegrationRepository(sqlite_db_manager, vault=vault)

    # 1. Tenant A stores Google connection
    conn_a = repo.upsert_connection(
        owner_id="tenant-alpha",
        provider="google",
        status=ConnectionStatus.CONNECTED.value,
        account_email="alpha@example.com",
        scopes=["https://www.googleapis.com/auth/calendar.readonly"],
        access_token="ya29.alpha_token_secret",
        refresh_token="1//alpha_refresh_secret",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    assert conn_a.owner_id == "tenant-alpha"
    assert conn_a.account_email == "alpha@example.com"
    assert conn_a.status == ConnectionStatus.CONNECTED

    # 2. Verify tokens are encrypted at rest in the database
    with sqlite_db_manager.session_scope() as session:
        from icarus_core.persistence.models import IntegrationConnectionModel

        raw_row = (
            session.query(IntegrationConnectionModel).filter_by(owner_id="tenant-alpha").first()
        )
        assert raw_row is not None
        assert "alpha_token_secret" not in raw_row.encrypted_access_token
        assert "alpha_refresh_secret" not in raw_row.encrypted_refresh_token

    # 3. Retrieve through repo decrypts tokens
    tokens = repo.get_connection_tokens(owner_id="tenant-alpha", provider="google")
    assert tokens is not None
    assert tokens["access_token"] == "ya29.alpha_token_secret"
    assert tokens["refresh_token"] == "1//alpha_refresh_secret"

    # 4. Tenant isolation: Tenant Beta cannot read Tenant Alpha's connection
    tenant_beta_repo = TenantIntegrationRepository(
        sqlite_db_manager, owner_id="tenant-beta", vault=vault
    )
    beta_connections = tenant_beta_repo.list_connections()
    assert len(beta_connections) == 0

    beta_tokens = tenant_beta_repo.get_tokens("google")
    assert beta_tokens is None


def test_oauth_state_single_use_replay_protection(sqlite_db_manager: DatabaseManager) -> None:
    vault = CredentialVault(allow_insecure_dev_key=True)
    repo = IntegrationRepository(sqlite_db_manager, vault=vault)

    # Create state
    repo.create_oauth_state(
        owner_id="tenant-1",
        provider="google",
        state="unique_state_xyz",
        redirect_uri="http://127.0.0.1:8000/v1/integrations/callback",
        expires_at=datetime.now(UTC) + timedelta(minutes=10),
        code_verifier="test_verifier_123",
        scopes=["email"],
    )

    # First consumption succeeds
    state_rec = repo.consume_oauth_state(state="unique_state_xyz", provider="google")
    assert state_rec is not None
    assert state_rec.code_verifier == "test_verifier_123"

    # Replay attempt fails (single-use anti-replay defense)
    replay_attempt = repo.consume_oauth_state(state="unique_state_xyz", provider="google")
    assert replay_attempt is None


# ---------------------------------------------------------------------------
# 5. FastAPI /v1/integrations Endpoints Tests
# ---------------------------------------------------------------------------


def test_fastapi_integrations_routes(
    sqlite_db_manager: DatabaseManager,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from icarus_api.config import ApiSettings

    vault = CredentialVault(allow_insecure_dev_key=True)
    settings = ApiSettings(auth_token="bootstrap-test-token")
    app = create_app(
        settings=settings,
        db_manager=sqlite_db_manager,
        credential_vault=vault,
    )

    auth_headers = {"Authorization": "Bearer bootstrap-test-token"}

    # Set GOOGLE_CLIENT_ID for testing
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-client-id-for-api")

    client = TestClient(app)

    # 1. GET /v1/integrations when empty
    resp = client.get("/v1/integrations", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json() == []

    # 2. POST /v1/integrations/authorize
    auth_payload = {
        "provider": "google",
        "redirect_uri": "http://localhost:8000/v1/integrations/callback",
    }
    auth_resp = client.post(
        "/v1/integrations/authorize",
        json=auth_payload,
        headers=auth_headers,
    )
    assert auth_resp.status_code == 200
    data = auth_resp.json()
    assert "authorization_url" in data
    assert "state" in data
    state = data["state"]

    # 3. Mock GoogleOAuthClient.exchange_code and get_account_email for callback
    with (
        patch.object(
            GoogleOAuthClient,
            "exchange_code",
            return_value={
                "access_token": "ya29.mock_api_token",
                "refresh_token": "1//mock_api_refresh",
                "expires_in": 3600,
            },
        ),
        patch.object(
            GoogleOAuthClient,
            "get_account_email",
            return_value="developer@example.com",
        ),
    ):
        # 4. GET /v1/integrations/callback (first attempt succeeds, callback does not require auth headers)
        cb_resp = client.get(
            f"/v1/integrations/callback?state={state}&code=test_auth_code_from_google"
        )
        assert cb_resp.status_code == 200
        cb_data = cb_resp.json()
        assert cb_data["status"] == "connected"
        assert cb_data["account_email"] == "developer@example.com"
        assert cb_data["provider"] == "google"

        # 5. Replay attempt fails with 400
        replay_resp = client.get(
            f"/v1/integrations/callback?state={state}&code=test_auth_code_from_google"
        )
        assert replay_resp.status_code == 400
        err_data = replay_resp.json()
        err_msg = err_data.get("error", {}).get("message") or err_data.get("detail", "")
        assert "Invalid, expired, or already used" in err_msg

    # 6. Verify connection appears in GET /v1/integrations
    list_resp = client.get("/v1/integrations", headers=auth_headers)
    assert list_resp.status_code == 200
    conns = list_resp.json()
    assert len(conns) == 1
    assert conns[0]["provider"] == "google"
    assert conns[0]["account_email"] == "developer@example.com"
    assert conns[0]["status"] == "connected"

    # 7. Disconnect /v1/integrations/google
    with patch.object(GoogleOAuthClient, "revoke_token", return_value=True):
        del_resp = client.delete("/v1/integrations/google", headers=auth_headers)
        assert del_resp.status_code == 200
        assert del_resp.json()["disconnected"] is True

    # 8. List is empty after disconnect
    after_del_resp = client.get("/v1/integrations", headers=auth_headers)
    assert after_del_resp.status_code == 200
    assert len(after_del_resp.json()) == 0
