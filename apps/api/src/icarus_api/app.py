"""FastAPI application factory and middleware configuration."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from icarus_core.persistence import DatabaseManager
from icarus_core.providers import ProviderRegistry
from icarus_core.security import AuditLogger, CredentialVault, SlidingWindowRateLimiter

from icarus_api.auth import TenantAuthMiddleware, TokenValidationCache
from icarus_api.config import ApiSettings
from icarus_api.errors import register_error_handlers
from icarus_api.lifespan import lifespan
from icarus_api.rate_limit import RateLimitMiddleware
from icarus_api.routes.health import router as health_router
from icarus_api.routes.runs import router as runs_router
from icarus_api.routes.sessions import router as sessions_router
from icarus_api.routes.tokens import router as tokens_router
from icarus_api.routes.vault import router as vault_router
from icarus_api.run_registry import ActiveRunRegistry


def create_app(
    settings: ApiSettings | None = None,
    db_manager: DatabaseManager | None = None,
    provider_registry: ProviderRegistry | None = None,
    run_registry: ActiveRunRegistry | None = None,
    token_cache: TokenValidationCache | None = None,
    credential_vault: CredentialVault | None = None,
    rate_limiter: SlidingWindowRateLimiter | None = None,
    audit_logger: AuditLogger | None = None,
) -> FastAPI:
    """Create and configure a new FastAPI application instance."""
    resolved_settings = settings or ApiSettings()

    app = FastAPI(
        title=resolved_settings.title,
        version=resolved_settings.version,
        description=resolved_settings.description,
        lifespan=lifespan,
    )

    app.state.settings = resolved_settings
    app.state.db_manager = db_manager
    app.state.provider_registry = provider_registry
    app.state.run_registry = run_registry
    app.state.token_cache = token_cache or TokenValidationCache()
    app.state.credential_vault = credential_vault or CredentialVault()
    app.state.rate_limiter = rate_limiter or SlidingWindowRateLimiter(
        default_rpm=resolved_settings.rate_limit_rpm,
        window_seconds=resolved_settings.rate_limit_window_seconds,
        max_concurrent_runs=resolved_settings.max_concurrent_runs_per_tenant,
    )
    app.state.audit_logger = audit_logger or AuditLogger(
        file_path=resolved_settings.audit_log_path,
        enabled=resolved_settings.audit_log_enabled,
    )

    # Configure CORS, rate limiting, and authentication middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=resolved_settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(TenantAuthMiddleware)

    # Register global structured error handlers
    register_error_handlers(app)

    # Include routes
    app.include_router(health_router)
    app.include_router(sessions_router)
    app.include_router(runs_router)
    app.include_router(tokens_router)
    app.include_router(vault_router)

    return app
