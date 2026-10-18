"""FastAPI application factory and middleware configuration."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from icarus_core.persistence import DatabaseManager

from icarus_api.config import ApiSettings
from icarus_api.errors import register_error_handlers
from icarus_api.lifespan import lifespan
from icarus_api.routes.health import router as health_router


def create_app(
    settings: ApiSettings | None = None,
    db_manager: DatabaseManager | None = None,
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

    # Configure CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=resolved_settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register global structured error handlers
    register_error_handlers(app)

    # Include routes
    app.include_router(health_router)

    return app

