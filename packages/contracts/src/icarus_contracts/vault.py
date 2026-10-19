"""Domain contracts and schemas for server-side credential vault and BYOK management."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class VaultCredentialCreate(BaseModel):
    """Payload to register or update an encrypted model provider API key."""

    provider: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="Provider identifier (e.g. openrouter, groq, anthropic, openai, grok)",
    )
    api_key: str = Field(
        ...,
        min_length=1,
        max_length=1024,
        description="Plaintext model provider API key to encrypt at rest",
    )


class VaultCredentialResponse(BaseModel):
    """Public representation of a stored vault credential with masked key preview."""

    provider: str = Field(..., description="Provider identifier")
    key_hint: str = Field(..., description="Masked key preview (e.g. 'sk-...4a2b')")
    created_at: datetime = Field(..., description="UTC creation timestamp")
    updated_at: datetime = Field(..., description="UTC update timestamp")


class VaultCredentialDeleteResponse(BaseModel):
    """Response returned upon deleting a vault credential."""

    provider: str = Field(..., description="Provider identifier")
    deleted: bool = Field(default=True, description="Whether credential was deleted")
