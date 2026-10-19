"""Domain contracts and schemas for token accounting and usage tracking."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class ApiTokenCreateRequest(BaseModel):
    """Payload to issue a new dynamic API access token."""

    name: str = Field(
        ..., min_length=1, max_length=128, description="Friendly label for the API token"
    )
    expires_at: datetime | None = Field(
        default=None, description="Optional UTC expiration timestamp"
    )


class ApiTokenResponse(BaseModel):
    """Public representation of an API token without raw secret."""

    id: str = Field(..., description="Unique UUID identifier for the token")
    owner_id: str = Field(..., description="Tenant owner ID")
    name: str = Field(..., description="Friendly token label")
    prefix: str = Field(..., description="Display prefix, e.g. sk_icarus_...4a2b")
    created_at: datetime = Field(..., description="UTC creation timestamp")
    expires_at: datetime | None = Field(
        default=None, description="Optional UTC expiration timestamp"
    )
    revoked_at: datetime | None = Field(
        default=None, description="UTC revocation timestamp if revoked"
    )
    last_used_at: datetime | None = Field(
        default=None, description="UTC timestamp of last authentication"
    )
    is_active: bool = Field(
        default=True, description="Whether the token is currently active and unexpired"
    )


class ApiTokenCreatedResponse(ApiTokenResponse):
    """Response returned upon token creation containing the plaintext secret."""

    token: str = Field(
        ..., description="Raw plaintext API token. Only returned once upon creation!"
    )


class ApiTokenRevokeResponse(BaseModel):
    """Response returned when revoking a token."""

    id: str = Field(..., description="Token UUID")
    revoked: bool = Field(default=True, description="Whether token was successfully revoked")
    revoked_at: datetime = Field(..., description="UTC revocation timestamp")


class ApiTokenListResponse(BaseModel):
    """List of API tokens belonging to the authenticated tenant."""

    tokens: list[ApiTokenResponse] = Field(default_factory=list)
    total: int = Field(default=0)


class TokenUsage(BaseModel):
    """Encapsulates prompt, completion, and total token usage metrics."""

    prompt_tokens: int = Field(default=0, ge=0)
    completion_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)

    def model_post_init(self, __context: object) -> None:
        """Ensure total_tokens reflects the sum of prompt and completion if not set."""
        if self.total_tokens == 0 and (self.prompt_tokens > 0 or self.completion_tokens > 0):
            self.total_tokens = self.prompt_tokens + self.completion_tokens

    def add(self, other: TokenUsage) -> TokenUsage:
        """Return a new TokenUsage instance representing the sum of this and another record."""
        return TokenUsage(
            prompt_tokens=self.prompt_tokens + other.prompt_tokens,
            completion_tokens=self.completion_tokens + other.completion_tokens,
            total_tokens=self.total_tokens + other.total_tokens,
        )

    def __add__(self, other: object) -> TokenUsage:
        if isinstance(other, TokenUsage):
            return self.add(other)
        return NotImplemented


class RunBudgetCounters(BaseModel):
    """Aggregated execution telemetry and token budget counters for an agent run."""

    prompt_tokens: int = Field(default=0, ge=0)
    completion_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)
    model_calls: int = Field(default=0, ge=0)
    tool_calls: int = Field(default=0, ge=0)
    compaction_count: int = Field(default=0, ge=0)
    elapsed_time_seconds: float = Field(default=0.0, ge=0.0)
    turns: int = Field(default=0, ge=0)
    compactions: int = Field(default=0, ge=0)
    finish_reason: str | None = None

    def model_post_init(self, __context: object) -> None:
        """Ensure total_tokens reflects prompt + completion if not set."""
        if self.total_tokens == 0 and (self.prompt_tokens > 0 or self.completion_tokens > 0):
            self.total_tokens = self.prompt_tokens + self.completion_tokens
        if self.compactions == 0 and self.compaction_count > 0:
            self.compactions = self.compaction_count
