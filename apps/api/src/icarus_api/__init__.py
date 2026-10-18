"""Icarus API server package."""

from icarus_api.app import create_app
from icarus_api.config import ApiSettings
from icarus_api.dependencies import (
    get_db_manager,
    get_db_session,
    get_message_repository,
    get_run_repository,
    get_session_repository,
    get_settings,
)

__version__ = "0.1.0"

__all__ = [
    "__version__",
    "ApiSettings",
    "create_app",
    "get_db_manager",
    "get_db_session",
    "get_message_repository",
    "get_run_repository",
    "get_session_repository",
    "get_settings",
]
