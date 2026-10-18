"""Health diagnostics and system status endpoints."""

import time
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter(tags=["Health"])


@router.get("/health")
async def get_health_liveness(request: Request) -> dict[str, Any]:
    """Liveness probe reporting application status, version, and uptime."""
    start_time = getattr(request.app.state, "start_time", time.monotonic())
    uptime = max(0.0, time.monotonic() - start_time)
    version = getattr(request.app.state.settings, "version", "0.1.0")

    return {
        "status": "ok",
        "version": version,
        "uptime_seconds": round(uptime, 4),
    }


@router.get("/health/ready")
async def get_health_readiness(request: Request) -> JSONResponse:
    """Readiness probe verifying database connectivity and engine responsiveness."""
    start_time = getattr(request.app.state, "start_time", time.monotonic())
    uptime = max(0.0, time.monotonic() - start_time)
    version = getattr(request.app.state.settings, "version", "0.1.0")

    db_manager = getattr(request.app.state, "db_manager", None)
    is_db_ok = False
    if db_manager is not None:
        try:
            is_db_ok = db_manager.is_connected()
        except Exception:
            is_db_ok = False

    status_code = 200 if is_db_ok else 503
    payload = {
        "status": "ok" if is_db_ok else "degraded",
        "database": "connected" if is_db_ok else "disconnected",
        "version": version,
        "uptime_seconds": round(uptime, 4),
    }

    return JSONResponse(status_code=status_code, content=payload)

