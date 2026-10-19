"""Authentication and tenant identity resolution for Icarus API."""

from __future__ import annotations

import secrets
import threading
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from icarus_contracts import TenantIdentity
from icarus_core.persistence import DatabaseManager
from icarus_core.persistence.models import TenantApiTokenModel
from icarus_core.security import hash_api_token
from sqlalchemy import select
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from icarus_api.config import ApiSettings

bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class CachedTokenEntry:
    """Immutable representation of a validated API token stored in memory."""

    token_id: str
    owner_id: str
    token_hash: str
    expires_at: datetime | None
    cached_at: float


class TokenValidationCache:
    """Thread-safe in-memory cache mapping token_hash -> CachedTokenEntry with TTL
    and instant invalidation.
    """

    def __init__(self, ttl_seconds: float = 300.0) -> None:
        self.ttl_seconds = ttl_seconds
        self._lock = threading.Lock()
        self._by_hash: dict[str, CachedTokenEntry] = {}
        self._token_id_to_hash: dict[str, str] = {}

    def get(self, token_hash: str) -> CachedTokenEntry | None:
        """Retrieve a cached token entry if present, unexpired by TTL and unexpired
        by token validity.
        """
        now_mono = time.monotonic()
        with self._lock:
            entry = self._by_hash.get(token_hash)
            if entry is None:
                return None
            if now_mono - entry.cached_at > self.ttl_seconds:
                self._evict_entry_unlocked(entry)
                return None
            if entry.expires_at is not None:
                exp = entry.expires_at
                if exp.tzinfo is None:
                    exp = exp.replace(tzinfo=UTC)
                if exp <= datetime.now(UTC):
                    self._evict_entry_unlocked(entry)
                    return None
            return entry

    def set(
        self,
        token_hash: str,
        token_id: str,
        owner_id: str,
        expires_at: datetime | None = None,
    ) -> None:
        """Store or update a validated token in the cache."""
        now_mono = time.monotonic()
        entry = CachedTokenEntry(
            token_id=token_id,
            owner_id=owner_id,
            token_hash=token_hash,
            expires_at=expires_at,
            cached_at=now_mono,
        )
        with self._lock:
            self._by_hash[token_hash] = entry
            self._token_id_to_hash[token_id] = token_hash

    def invalidate_by_token_id(self, token_id: str) -> bool:
        """Immediately purge a token from cache by its unique ID."""
        with self._lock:
            token_hash = self._token_id_to_hash.pop(token_id, None)
            if token_hash is not None:
                self._by_hash.pop(token_hash, None)
                return True
            return False

    def invalidate_by_token_hash(self, token_hash: str) -> bool:
        """Immediately purge a token from cache by its SHA-256 hash."""
        with self._lock:
            entry = self._by_hash.pop(token_hash, None)
            if entry is not None:
                self._token_id_to_hash.pop(entry.token_id, None)
                return True
            return False

    def clear(self) -> None:
        """Clear all cached tokens."""
        with self._lock:
            self._by_hash.clear()
            self._token_id_to_hash.clear()

    def _evict_entry_unlocked(self, entry: CachedTokenEntry) -> None:
        self._by_hash.pop(entry.token_hash, None)
        self._token_id_to_hash.pop(entry.token_id, None)


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


def resolve_tenant_identity(
    token: str,
    settings: ApiSettings,
    db_manager: DatabaseManager | None = None,
    token_cache: TokenValidationCache | None = None,
) -> TenantIdentity | None:
    """Validate a bearer/API token against dynamic database store and static settings."""
    if not token:
        return None

    # 1. First, check dynamic database-backed tokens if db_manager is available
    if db_manager is not None:
        candidate_hash = hash_api_token(token)

        # Check in-memory token cache first
        if token_cache is not None:
            cached = token_cache.get(candidate_hash)
            if cached is not None:
                return TenantIdentity(owner_id=cached.owner_id, token=token)

        # Cache miss: query database
        with db_manager.session_scope() as session:
            stmt = select(TenantApiTokenModel).where(
                TenantApiTokenModel.token_hash == candidate_hash
            )
            model = session.execute(stmt).scalar_one_or_none()
            if model is not None:
                # Constant-time comparison on hash
                if not secrets.compare_digest(model.token_hash, candidate_hash):
                    return None
                # Check revocation
                if model.revoked_at is not None:
                    return None
                # Check expiration
                now = datetime.now(UTC)
                exp = model.expires_at
                if exp is not None:
                    if exp.tzinfo is None:
                        exp = exp.replace(tzinfo=UTC)
                    if exp <= now:
                        return None

                # Valid token! Update last_used_at
                model.last_used_at = now
                session.flush()

                # Populate cache
                if token_cache is not None:
                    token_cache.set(
                        token_hash=candidate_hash,
                        token_id=model.id,
                        owner_id=model.owner_id,
                        expires_at=model.expires_at,
                    )

                return TenantIdentity(owner_id=model.owner_id, token=token)

    # 2. Check explicit multi-tenant token mapping
    if settings.auth_tokens and token in settings.auth_tokens:
        owner_id = settings.auth_tokens[token]
        return TenantIdentity(owner_id=owner_id, token=token)

    # 3. Check scoped token (e.g. "tenant-id:master-secret")
    if settings.auth_token and ":" in token:
        prefix, _, secret = token.partition(":")
        if prefix and secrets.compare_digest(secret, settings.auth_token):
            return TenantIdentity(owner_id=prefix, token=token)

    # 4. Check single service master secret (ICARUS_API_AUTH_TOKEN)
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

    # Resolve settings and DB/cache dependencies if available
    resolved_settings = settings or getattr(request.app.state, "settings", None) or ApiSettings()
    db_manager = getattr(request.app.state, "db_manager", None)
    token_cache = getattr(request.app.state, "token_cache", None)

    identity = resolve_tenant_identity(
        token=token,
        settings=resolved_settings,
        db_manager=db_manager,
        token_cache=token_cache,
    )
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
            db_manager = getattr(request.app.state, "db_manager", None)
            token_cache = getattr(request.app.state, "token_cache", None)
            identity = resolve_tenant_identity(
                token=token,
                settings=settings,
                db_manager=db_manager,
                token_cache=token_cache,
            )
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
