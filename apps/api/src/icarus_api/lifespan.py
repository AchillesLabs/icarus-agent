"""Application lifespan context manager for FastAPI."""

import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from icarus_core.persistence import DatabaseManager


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, Any]:
    """Manage application startup and shutdown lifecycle hooks."""
    app.state.start_time = time.monotonic()

    # If db_manager was not injected, initialize default DatabaseManager
    if not hasattr(app.state, "db_manager") or app.state.db_manager is None:
        db_url = getattr(app.state.settings, "database_url", None)
        app.state.db_manager = DatabaseManager(db_url=db_url)

    if not hasattr(app.state, "token_cache") or app.state.token_cache is None:
        from icarus_api.auth import TokenValidationCache

        app.state.token_cache = TokenValidationCache()

    yield

    # Shutdown: clean up database connections
    if hasattr(app.state, "db_manager") and app.state.db_manager is not None:
        app.state.db_manager.close()
