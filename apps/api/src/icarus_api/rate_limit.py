"""Rate limiting middleware enforcing sliding-window quotas and RFC 6585 headers."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from fastapi import Request, Response, status
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from icarus_api.config import ApiSettings
from icarus_api.errors import create_error_response

if TYPE_CHECKING:
    from icarus_core.security import SlidingWindowRateLimiter

logger = logging.getLogger("icarus.rate_limit")


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Middleware enforcing sliding-window rate limits per tenant identity or client IP.

    Injects RFC 6585 and de-facto standard headers on every evaluated response:
      - X-RateLimit-Limit: total allowed requests in window
      - X-RateLimit-Remaining: remaining requests available in window
      - X-RateLimit-Reset: seconds until window resets
    When the threshold is exceeded, returns HTTP 429 Too Many Requests with a Retry-After header.
    """

    EXEMPT_PATHS = {
        "/health",
        "/health/ready",
        "/docs",
        "/openapi.json",
        "/redoc",
    }

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # Preflight CORS requests are always exempt
        if request.method == "OPTIONS":
            return await call_next(request)

        # Health checks, readiness probes, and API documentation are exempt
        if request.url.path in self.EXEMPT_PATHS:
            return await call_next(request)

        settings: ApiSettings = getattr(request.app.state, "settings", None) or ApiSettings()
        if not getattr(settings, "rate_limit_enabled", True):
            return await call_next(request)

        rate_limiter: SlidingWindowRateLimiter | None = getattr(
            request.app.state, "rate_limiter", None
        )
        if rate_limiter is None:
            return await call_next(request)

        # Derive rate limit key based on verified tenant identity if authenticated, otherwise IP
        owner_id = getattr(request.state, "owner_id", None)
        if owner_id:
            key = f"tenant:{owner_id}"
        else:
            client_host = request.client.host if request.client else "unknown"
            key = f"ip:{client_host}"

        result = rate_limiter.check_rate_limit(key)
        if not result.allowed:
            logger.warning(
                "Rate limit exceeded for key %s (limit=%s, retry_after=%ss)",
                key,
                result.limit,
                result.retry_after,
            )
            audit_logger = getattr(request.app.state, "audit_logger", None)
            if audit_logger:
                audit_logger.log_rate_limit_exceeded(
                    actor_id=owner_id,
                    client_ip=request.client.host if request.client else None,
                    user_agent=request.headers.get("user-agent"),
                    resource=request.url.path,
                    limit=result.limit,
                    retry_after=result.retry_after,
                    details={"key": key},
                )
            return create_error_response(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                message=f"Rate limit exceeded. Try again in {result.retry_after} seconds.",
                code="rate_limited",
                details={
                    "limit": result.limit,
                    "remaining": 0,
                    "retry_after": result.retry_after,
                    "reset_seconds": result.reset_seconds,
                },
                headers={
                    "Retry-After": str(result.retry_after),
                    "X-RateLimit-Limit": str(result.limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(result.reset_seconds),
                },
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(result.limit)
        response.headers["X-RateLimit-Remaining"] = str(result.remaining)
        response.headers["X-RateLimit-Reset"] = str(result.reset_seconds)
        return response
