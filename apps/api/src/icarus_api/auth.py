"""Authentication and tenant identity resolution for Icarus API."""

import secrets
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from icarus_contracts import TenantIdentity
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from icarus_api.config import ApiSettings

bearer_scheme = HTTPBearer(auto_error=False)


def get_settings(request: Request) -> ApiSettings:
    """Resolve active application settings from request state."""
    settings = getattr(request.app.state, "settings", None)
    if settings is None:
        settings = ApiSettings()
        request.app.state.settings = settings
    return settings


def extract_token_from_request(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = None,
) -> str | None:
    """Extract raw token string from HTTPAuthorizationCredentials,
    Authorization header, or X-API-Key.
    """
    if credentials is not None and credentials.credentials:
        return credentials.credentials.strip()

    auth_header = request.headers.get("Authorization")
    if auth_header:
        parts = auth_header.strip().split(" ", 1)
        if len(parts) == 2 and parts[0].lower() == "bearer":
            return parts[1].strip()
        # If bare token was passed in Authorization header
        return auth_header.strip()

    api_key_header = request.headers.get("X-API-Key") or request.headers.get("x-api-key")
    if api_key_header:
        return api_key_header.strip()

    return None


def resolve_tenant_identity(token: str, settings: ApiSettings) -> TenantIdentity | None:
    """Validate a bearer/API token against settings and resolve the TenantIdentity."""
    if not token:
        return None

    # 1. Check explicit multi-tenant token mapping
    if settings.auth_tokens and token in settings.auth_tokens:
        owner_id = settings.auth_tokens[token]
        return TenantIdentity(owner_id=owner_id, token=token)

    # 2. Check scoped token (e.g. "tenant-id:master-secret")
    if settings.auth_token and ":" in token:
        prefix, _, secret = token.partition(":")
        if prefix and secrets.compare_digest(secret, settings.auth_token):
            return TenantIdentity(owner_id=prefix, token=token)

    # 3. Check single service master secret (ICARUS_API_AUTH_TOKEN)
    if settings.auth_token and secrets.compare_digest(token, settings.auth_token):
        return TenantIdentity(owner_id=settings.default_owner_id, token=token)

    return None


async def get_current_tenant(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)] = None,
    settings: Annotated[ApiSettings, Depends(get_settings)] = None,
) -> TenantIdentity:
    """Security dependency validating Bearer or API Key credentials and returning TenantIdentity."""
    # Check if identity was already resolved and bound by middleware
    bound_identity = getattr(request.state, "identity", None)
    if bound_identity is not None and isinstance(bound_identity, TenantIdentity):
        return bound_identity

    # Extract token
    token = extract_token_from_request(request, credentials)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication credentials were not provided",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Resolve settings if not provided
    resolved_settings = settings or getattr(request.app.state, "settings", None) or ApiSettings()
    identity = resolve_tenant_identity(token, resolved_settings)
    if identity is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Bind immutable identity into request state
    request.state.identity = identity
    request.state.owner_id = identity.owner_id
    return identity


def get_tenant_owner_id(
    identity: Annotated[TenantIdentity, Depends(get_current_tenant)],
) -> str:
    """Convenience dependency resolving only the verified immutable owner_id string."""
    return identity.owner_id


class TenantAuthMiddleware(BaseHTTPMiddleware):
    """Middleware extracting and binding authenticated TenantIdentity into request state."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        settings = getattr(request.app.state, "settings", None)
        if settings is None:
            settings = ApiSettings()
            request.app.state.settings = settings

        token = extract_token_from_request(request)
        if token:
            identity = resolve_tenant_identity(token, settings)
            if identity is not None:
                request.state.identity = identity
                request.state.owner_id = identity.owner_id
            else:
                request.state.identity = None
                request.state.owner_id = None
        else:
            request.state.identity = None
            request.state.owner_id = None

        return await call_next(request)
