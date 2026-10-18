"""Domain contracts and schemas for token accounting and usage tracking."""

from __future__ import annotations

from pydantic import BaseModel, Field


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
