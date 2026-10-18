"""Icarus API server package."""

from icarus_api.app import create_app
from icarus_api.auth import (
    TenantAuthMiddleware,
    get_current_tenant,
    get_tenant_owner_id,
    resolve_tenant_identity,
)
from icarus_api.config import ApiSettings
from icarus_api.dependencies import (
    get_db_manager,
    get_db_session,
    get_message_repository,
    get_run_repository,
    get_session_repository,
    get_settings,
    get_tenant_db_session,
    get_tenant_message_repository,
    get_tenant_run_repository,
    get_tenant_session,
    get_tenant_session_repository,
)

__version__ = "0.1.0"

__all__ = [
    "__version__",
    "ApiSettings",
    "TenantAuthMiddleware",
    "create_app",
    "get_current_tenant",
    "get_db_manager",
    "get_db_session",
    "get_message_repository",
    "get_run_repository",
    "get_session_repository",
    "get_settings",
    "get_tenant_db_session",
    "get_tenant_message_repository",
    "get_tenant_owner_id",
    "get_tenant_run_repository",
    "get_tenant_session",
    "get_tenant_session_repository",
    "resolve_tenant_identity",
]
