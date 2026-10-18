"""Tenant and principal identity contracts."""

from pydantic import BaseModel, ConfigDict, Field


class TenantIdentity(BaseModel):
    """Authenticated tenant identity representing an execution principal."""

    model_config = ConfigDict(frozen=True)

    owner_id: str = Field(
        ...,
        min_length=1,
        description="Immutable tenant or user identity ID.",
    )
    token: str | None = Field(
        default=None,
        repr=False,
        description="Bearer token or API key used to authenticate.",
    )
