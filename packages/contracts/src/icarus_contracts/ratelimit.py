"""Domain contracts and schemas for rate limiting and concurrency throttling."""

from __future__ import annotations

from pydantic import BaseModel, Field


class RateLimitConfig(BaseModel):
    """Configuration parameters for rate limiting and execution concurrency."""

    enabled: bool = Field(default=True, description="Whether rate limiting is enabled")
    default_rpm: int = Field(
        default=60, ge=1, description="Default requests per minute ceiling per tenant"
    )
    window_seconds: float = Field(
        default=60.0, ge=1.0, description="Sliding window duration in seconds"
    )
    max_concurrent_runs: int = Field(
        default=5, ge=1, description="Maximum concurrent active agent runs per tenant"
    )


class RateLimitStatus(BaseModel):
    """Detailed status result of a rate limit check."""

    allowed: bool = Field(..., description="Whether the request was allowed")
    limit: int = Field(..., description="Maximum allowed requests in the sliding window")
    remaining: int = Field(..., description="Remaining requests allowed in the current window")
    reset_seconds: int = Field(..., description="Seconds until the sliding window resets")
    retry_after: int = Field(default=0, description="Seconds caller must wait before retrying")
