"""Global exception handlers for structured and normalized JSON error payloads."""

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from icarus_contracts import TenantAccessDeniedError
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)

STATUS_CODE_TO_ERROR_CODE = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    408: "request_timeout",
    409: "conflict",
    422: "validation_error",
    429: "rate_limited",
    500: "internal_server_error",
    502: "bad_gateway",
    503: "service_unavailable",
    504: "gateway_timeout",
}


def create_error_response(
    status_code: int,
    message: str,
    code: str | None = None,
    details: Any = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    """Build a standardized JSON error response."""
    error_code = code or STATUS_CODE_TO_ERROR_CODE.get(status_code, "error")
    return JSONResponse(
        status_code=status_code,
        headers=headers,
        content={
            "error": {
                "code": error_code,
                "message": message,
                "details": details,
            }
        },
    )


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Handle standard HTTP exceptions with normalized envelope."""
    message = exc.detail if isinstance(exc.detail, str) else "HTTP error"
    details = exc.detail if not isinstance(exc.detail, str) else None
    return create_error_response(
        status_code=exc.status_code,
        message=message,
        details=details,
        headers=getattr(exc, "headers", None),
    )


async def tenant_access_denied_handler(
    request: Request,
    exc: TenantAccessDeniedError,
) -> JSONResponse:
    """Handle tenant isolation violations returning 403 Forbidden."""
    audit_logger = getattr(request.app.state, "audit_logger", None)
    if audit_logger:
        audit_logger.log_access_denied(
            actor_id=getattr(request.state, "owner_id", None),
            client_ip=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
            resource=request.url.path,
            reason=str(exc),
        )
    return create_error_response(
        status_code=403,
        code="forbidden",
        message=str(exc),
        details=None,
    )


async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    """Handle Pydantic/FastAPI request validation errors."""
    return create_error_response(
        status_code=422,
        code="validation_error",
        message="Request validation failed",
        details=exc.errors(),
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all for unhandled exceptions returning 500 error envelope."""
    logger.exception("Unhandled server exception: %s", exc)
    return create_error_response(
        status_code=500,
        code="internal_server_error",
        message="An internal server error occurred",
        details=None,
    )


def register_error_handlers(app: FastAPI) -> None:
    """Register all global error handlers onto the FastAPI application."""
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(TenantAccessDeniedError, tenant_access_denied_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
