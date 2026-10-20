"""FastAPI routes for tenant-isolated application integrations and OAuth lifecycles."""

from __future__ import annotations

import contextlib
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from icarus_contracts.identity import TenantIdentity
from icarus_contracts.integrations import (
    ConnectionStatus,
    IntegrationConnection,
    OAuthAuthorizationInitiate,
    OAuthAuthorizationRequest,
    OAuthCallbackResult,
)
from icarus_core.integrations.google import (
    GOOGLE_MANIFEST,
    GoogleOAuthClient,
    GoogleOAuthError,
)
from icarus_core.persistence import (
    DatabaseManager,
    IntegrationRepository,
    TenantIntegrationRepository,
)
from icarus_core.security import CredentialVault

from icarus_api.dependencies import (
    get_credential_vault,
    get_current_tenant,
    get_db_manager,
    get_tenant_integration_repository,
)

router = APIRouter(prefix="/v1/integrations", tags=["Integrations"])


@router.get(
    "",
    response_model=list[IntegrationConnection],
    status_code=status.HTTP_200_OK,
    summary="List configured app connections for authenticated tenant",
)
async def list_integrations(
    repo: Annotated[TenantIntegrationRepository, Depends(get_tenant_integration_repository)],
) -> list[IntegrationConnection]:
    """Retrieve all external application connections belonging to the authenticated tenant."""
    return repo.list_connections()


@router.post(
    "/authorize",
    response_model=OAuthAuthorizationRequest,
    status_code=status.HTTP_200_OK,
    summary="Initiate OAuth 2.0 PKCE authorization flow",
)
@router.post(
    "/{provider}/authorize",
    response_model=OAuthAuthorizationRequest,
    status_code=status.HTTP_200_OK,
    summary="Initiate OAuth 2.0 PKCE authorization flow",
)
async def start_oauth_flow(
    identity: Annotated[TenantIdentity, Depends(get_current_tenant)],
    repo: Annotated[TenantIntegrationRepository, Depends(get_tenant_integration_repository)],
    request: Request,
    provider: str = "google",
    redirect_uri: str | None = Query(None),
    payload: OAuthAuthorizationInitiate | None = None,
) -> OAuthAuthorizationRequest:
    """Generate cryptographically secure PKCE challenge, bind state to tenant, and return auth URL."""
    norm_provider = provider.strip().lower()
    if payload and payload.provider:
        norm_provider = payload.provider.strip().lower()

    if norm_provider != "google":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"OAuth provider '{norm_provider}' is not supported.",
        )

    resolved_redirect = redirect_uri or (payload.redirect_uri if payload else None)
    if not resolved_redirect:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing required 'redirect_uri' parameter.",
        )

    client = GoogleOAuthClient()
    if not client.is_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google OAuth client is not configured on this server (missing GOOGLE_CLIENT_ID).",
        )

    try:
        auth_url, state, code_verifier = client.create_authorization_flow(
            redirect_uri=resolved_redirect,
        )
    except GoogleOAuthError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    expires_at = datetime.now(UTC) + timedelta(minutes=10)
    repo.create_oauth_state(
        provider=norm_provider,
        state=state,
        redirect_uri=resolved_redirect,
        expires_at=expires_at,
        code_verifier=code_verifier,
        scopes=GOOGLE_MANIFEST.required_scopes,
    )

    return OAuthAuthorizationRequest(
        provider=norm_provider,
        authorization_url=auth_url,
        state=state,
        code_verifier=code_verifier,
        redirect_uri=resolved_redirect,
        expires_at=expires_at,
    )


@router.get(
    "/callback",
    response_model=OAuthCallbackResult,
    status_code=status.HTTP_200_OK,
    summary="Handle OAuth redirect callback and securely exchange tokens",
)
@router.get(
    "/{provider}/callback",
    response_model=OAuthCallbackResult,
    status_code=status.HTTP_200_OK,
    summary="Handle OAuth redirect callback and securely exchange tokens",
)
@router.post(
    "/callback",
    response_model=OAuthCallbackResult,
    status_code=status.HTTP_200_OK,
    summary="Handle OAuth redirect callback (POST) and securely exchange tokens",
)
@router.post(
    "/{provider}/callback",
    response_model=OAuthCallbackResult,
    status_code=status.HTTP_200_OK,
    summary="Handle OAuth redirect callback (POST) and securely exchange tokens",
)
async def handle_oauth_callback(
    state: str,
    db_manager: Annotated[DatabaseManager, Depends(get_db_manager)],
    vault: Annotated[CredentialVault, Depends(get_credential_vault)],
    provider: str = "google",
    code: str | None = None,
    error: str | None = None,
) -> OAuthCallbackResult:
    """Validate one-time state, verify tenant ownership, and exchange code with provider."""
    norm_provider = provider.strip().lower()
    if error:
        return OAuthCallbackResult(
            provider=norm_provider,
            status=ConnectionStatus.FAILED,
            error=f"Provider reported authorization failure: {error}",
        )

    if not code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing required 'code' parameter in callback.",
        )

    # 1. Atomically consume OAuth state ensuring replay prevention and resolving tenant binding
    global_repo = IntegrationRepository(db_manager, vault=vault)
    oauth_state_model = global_repo.consume_oauth_state(state)
    if oauth_state_model is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid, expired, or already used OAuth state token.",
        )

    # 2. Exchange authorization code with provider using stored PKCE verifier
    client = GoogleOAuthClient()
    try:
        token_data = client.exchange_code(
            code=code,
            redirect_uri=oauth_state_model.redirect_uri,
            code_verifier=oauth_state_model.code_verifier or "",
        )
    except GoogleOAuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Token exchange failed: {exc}",
        ) from exc

    access_token = token_data.get("access_token")
    refresh_token = token_data.get("refresh_token")
    expires_in = token_data.get("expires_in", 3600)
    token_type = token_data.get("token_type", "Bearer")
    scope_str = token_data.get("scope", "")
    granted_scopes = scope_str.split() if scope_str else []

    expires_at = datetime.now(UTC) + timedelta(seconds=int(expires_in))

    # 3. Retrieve user email identity for connection preview
    account_email = client.get_account_email(access_token) if access_token else None

    # 4. Encrypt and persist connection under the verified tenant owner_id
    global_repo.set_connection(
        owner_id=oauth_state_model.owner_id,
        provider=norm_provider,
        status=ConnectionStatus.CONNECTED.value,
        access_token=access_token,
        refresh_token=refresh_token,
        token_type=token_type,
        scopes=granted_scopes,
        account_email=account_email,
        expires_at=expires_at,
        metadata={"email": account_email},
    )

    return OAuthCallbackResult(
        provider=norm_provider,
        status=ConnectionStatus.CONNECTED,
        account_email=account_email,
        granted_scopes=granted_scopes,
    )


@router.get(
    "/{provider}",
    response_model=IntegrationConnection,
    status_code=status.HTTP_200_OK,
    summary="Get status and metadata for a specific integration",
)
async def get_integration(
    provider: str,
    repo: Annotated[TenantIntegrationRepository, Depends(get_tenant_integration_repository)],
) -> IntegrationConnection:
    """Retrieve connection status and granted scopes for a specific provider (tokens omitted)."""
    conn = repo.get_connection(provider)
    if conn is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Integration '{provider}' not connected for this tenant.",
        )
    return conn


@router.delete(
    "/{provider}",
    status_code=status.HTTP_200_OK,
    summary="Disconnect integration and revoke external account tokens",
)
async def disconnect_integration(
    provider: str,
    repo: Annotated[TenantIntegrationRepository, Depends(get_tenant_integration_repository)],
) -> dict[str, Any]:
    """Revoke tokens at the provider and delete stored integration connection."""
    norm_provider = provider.strip().lower()
    access_tok, refresh_tok = repo.get_decrypted_tokens(norm_provider)

    # Attempt upstream provider revocation if token exists
    if access_tok or refresh_tok:
        tok_to_revoke = refresh_tok or access_tok
        client = GoogleOAuthClient()
        if tok_to_revoke:
            with contextlib.suppress(Exception):
                client.revoke_token(tok_to_revoke)

    deleted = repo.delete_connection(norm_provider)
    return {
        "provider": norm_provider,
        "disconnected": True,
        "deleted": deleted,
    }
