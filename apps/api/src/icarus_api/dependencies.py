"""Dependency injection providers for FastAPI routes."""

from collections.abc import Generator
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from icarus_contracts import TenantIdentity
from icarus_contracts.session import SessionDTO
from icarus_core.persistence import (
    AgentRunRepository,
    DatabaseManager,
    MessageRepository,
    SessionRepository,
    TenantApiTokenRepository,
    TenantCredentialRepository,
    TenantMessageRepository,
    TenantRunRepository,
    TenantSessionRepository,
)
from icarus_core.providers import ProviderRegistry
from icarus_core.security import AuditLogger, CredentialVault, SlidingWindowRateLimiter
from sqlalchemy.orm import Session

from icarus_api.auth import TokenValidationCache, get_current_tenant, get_settings
from icarus_api.run_registry import ActiveRunRegistry


def get_db_manager(request: Request) -> DatabaseManager:
    """Resolve active DatabaseManager from request state."""
    db_manager = getattr(request.app.state, "db_manager", None)
    if db_manager is None:
        settings = get_settings(request)
        db_manager = DatabaseManager(db_url=settings.database_url)
        request.app.state.db_manager = db_manager
    return db_manager


def get_db_session(
    db_manager: Annotated[DatabaseManager, Depends(get_db_manager)],
) -> Generator[Session, None, None]:
    """Provide a transactional session scope for the duration of a request."""
    with db_manager.session_scope() as session:
        yield session


def get_session_repository(
    session: Annotated[Session, Depends(get_db_session)],
) -> SessionRepository:
    """Provide a SessionRepository bound to the current request's session."""
    return SessionRepository(session)


def get_message_repository(
    session: Annotated[Session, Depends(get_db_session)],
) -> MessageRepository:
    """Provide a MessageRepository bound to the current request's session."""
    return MessageRepository(session)


def get_run_repository(
    session: Annotated[Session, Depends(get_db_session)],
) -> AgentRunRepository:
    """Provide an AgentRunRepository bound to the current request's session."""
    return AgentRunRepository(session)


def get_tenant_db_session(
    identity: Annotated[TenantIdentity, Depends(get_current_tenant)],
    db_manager: Annotated[DatabaseManager, Depends(get_db_manager)],
) -> Generator[Session, None, None]:
    """Provide a transactional session scope bound to the authenticated tenant."""
    with db_manager.session_scope() as session:
        session.info["owner_id"] = identity.owner_id
        session.info["tenant_identity"] = identity
        yield session


def get_tenant_session_repository(
    identity: Annotated[TenantIdentity, Depends(get_current_tenant)],
    db_manager: Annotated[DatabaseManager, Depends(get_db_manager)],
) -> TenantSessionRepository:
    """Provide a SessionRepository scoped to the authenticated tenant."""
    return TenantSessionRepository(db_manager=db_manager, owner_id=identity.owner_id)


def get_tenant_message_repository(
    identity: Annotated[TenantIdentity, Depends(get_current_tenant)],
    db_manager: Annotated[DatabaseManager, Depends(get_db_manager)],
) -> TenantMessageRepository:
    """Provide a MessageRepository scoped to the authenticated tenant."""
    return TenantMessageRepository(db_manager=db_manager, owner_id=identity.owner_id)


def get_tenant_run_repository(
    identity: Annotated[TenantIdentity, Depends(get_current_tenant)],
    db_manager: Annotated[DatabaseManager, Depends(get_db_manager)],
) -> TenantRunRepository:
    """Provide an AgentRunRepository scoped to the authenticated tenant."""
    return TenantRunRepository(db_manager=db_manager, owner_id=identity.owner_id)


def get_tenant_session(
    session_id: str,
    repo: Annotated[TenantSessionRepository, Depends(get_tenant_session_repository)],
) -> SessionDTO:
    """Resolve an existing session ensuring it belongs to the authenticated tenant, or 404."""
    session = repo.get_session(session_id)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session '{session_id}' not found",
        )
    return session


def get_active_run_registry(request: Request) -> ActiveRunRegistry:
    """Resolve or initialize the in-memory active run registry."""
    registry = getattr(request.app.state, "run_registry", None)
    if registry is None:
        registry = ActiveRunRegistry()
        request.app.state.run_registry = registry
    return registry


def get_provider_registry(request: Request) -> ProviderRegistry:
    """Resolve or initialize the model provider registry."""
    registry = getattr(request.app.state, "provider_registry", None)
    if registry is None:
        registry = ProviderRegistry()
        request.app.state.provider_registry = registry
    return registry


def get_token_cache(request: Request) -> TokenValidationCache:
    """Resolve or initialize the in-memory token validation cache."""
    cache = getattr(request.app.state, "token_cache", None)
    if cache is None:
        cache = TokenValidationCache()
        request.app.state.token_cache = cache
    return cache


def get_tenant_api_token_repository(
    identity: Annotated[TenantIdentity, Depends(get_current_tenant)],
    db_manager: Annotated[DatabaseManager, Depends(get_db_manager)],
) -> TenantApiTokenRepository:
    """Provide a TenantApiTokenRepository scoped to the authenticated tenant."""
    return TenantApiTokenRepository(db_manager=db_manager, owner_id=identity.owner_id)


def get_credential_vault(request: Request) -> CredentialVault:
    """Resolve active CredentialVault from application state."""
    vault = getattr(request.app.state, "credential_vault", None)
    if vault is None:
        vault = CredentialVault()
        request.app.state.credential_vault = vault
    return vault


def get_tenant_credential_repository(
    identity: Annotated[TenantIdentity, Depends(get_current_tenant)],
    db_manager: Annotated[DatabaseManager, Depends(get_db_manager)],
    vault: Annotated[CredentialVault, Depends(get_credential_vault)],
) -> TenantCredentialRepository:
    """Provide a TenantCredentialRepository scoped to the authenticated tenant."""
    return TenantCredentialRepository(
        db_manager=db_manager,
        owner_id=identity.owner_id,
        vault=vault,
    )


def get_rate_limiter(request: Request) -> SlidingWindowRateLimiter:
    """Resolve active SlidingWindowRateLimiter from application state."""
    limiter = getattr(request.app.state, "rate_limiter", None)
    if limiter is None:
        settings = get_settings(request)
        limiter = SlidingWindowRateLimiter(
            default_rpm=settings.rate_limit_rpm,
            window_seconds=settings.rate_limit_window_seconds,
            max_concurrent_runs=settings.max_concurrent_runs_per_tenant,
        )
        request.app.state.rate_limiter = limiter
    return limiter


def get_audit_logger(request: Request) -> AuditLogger:
    """Resolve active AuditLogger from application state."""
    logger = getattr(request.app.state, "audit_logger", None)
    if logger is None:
        settings = get_settings(request)
        logger = AuditLogger(
            file_path=settings.audit_log_path,
            enabled=settings.audit_log_enabled,
        )
        request.app.state.audit_logger = logger
    return logger
