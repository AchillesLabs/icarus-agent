"""Contracts for configuration management and credential resolution."""

from enum import StrEnum

from pydantic import BaseModel, Field


class CredentialSource(StrEnum):
    """Source from which a secret credential was resolved."""

    CLI_ARG = "cli_arg"
    ENV_VAR = "env_var"
    KEYRING = "keyring"
    NONE = "none"


class CredentialResult(BaseModel):
    """Resolved credential status and metadata."""

    provider: str
    secret: str | None = None
    source: CredentialSource = CredentialSource.NONE
    masked: str | None = None

    @property
    def is_available(self) -> bool:
        """Return True if a non-empty credential was successfully resolved."""
        return self.secret is not None and len(self.secret.strip()) > 0


class IcarusConfig(BaseModel):
    """Configuration settings stored in ~/.icarus/config.toml (non-sensitive only)."""

    default_provider: str = Field(default="grok", description="Default AI model provider")
    model: str = Field(default="grok-2", description="Default model name identifier")
    temperature: float = Field(default=0.7, ge=0.0, le=2.0, description="Sampling temperature")
    max_turns: int = Field(default=25, ge=1, le=200, description="Maximum execution turns per run")
    max_tokens_budget: int = Field(
        default=128000,
        ge=1000,
        le=2000000,
        description="Maximum context token budget",
    )
    safety_margin_tokens: int = Field(
        default=2000,
        ge=0,
        le=50000,
        description="Safety buffer tokens to prevent hitting provider limits",
    )
    output_reserve_tokens: int = Field(
        default=4000,
        ge=100,
        le=64000,
        description="Reserved tokens for model completion generation",
    )
    compaction_threshold: float = Field(
        default=0.8,
        ge=0.1,
        le=1.0,
        description="Context utilization threshold triggering compaction",
    )
