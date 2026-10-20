"""Domain models and typed contracts for external application integrations and OAuth lifecycles."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Protocol

from pydantic import BaseModel, Field


class ConnectionStatus(str, Enum):
    """Lifecycle connection status for an external application integration."""

    DISCONNECTED = "disconnected"
    AUTHORIZING = "authorizing"
    CONNECTED = "connected"
    NEEDS_REAUTH = "needs_reauth"
    FAILED = "failed"


class AuthMethod(str, Enum):
    """Authentication mechanism utilized by the integration provider."""

    OAUTH2_PKCE = "oauth2_pkce"
    API_KEY = "api_key"
    BEARER_TOKEN = "bearer_token"


class IntegrationManifest(BaseModel):
    """Static metadata and permission definition for an integration provider."""

    id: str = Field(..., description="Stable provider identifier (e.g. google, github, slack)")
    display_name: str = Field(..., description="Human-friendly integration title")
    description: str = Field(..., description="Detailed explanation of capabilities provided")
    auth_method: AuthMethod = Field(
        default=AuthMethod.OAUTH2_PKCE,
        description="Authentication method required",
    )
    required_scopes: list[str] = Field(
        default_factory=list,
        description="OAuth scopes or permissions requested by this integration",
    )
    tools: list[str] = Field(
        default_factory=list,
        description="List of tool names registered by this integration",
    )
    required_config: list[str] = Field(
        default_factory=list,
        description="Configuration keys or client credentials required from the operator",
    )
    supported_modes: list[str] = Field(
        default_factory=lambda: ["local", "hosted"],
        description="Supported execution modes (e.g. local CLI, hosted API)",
    )


class IntegrationConnection(BaseModel):
    """Public representation of an authenticated tenant integration connection.

    Notice: Raw access tokens and refresh tokens are strictly omitted to prevent leakage.
    """

    id: str = Field(..., description="Unique connection record ID")
    owner_id: str = Field(..., description="Tenant or user identifier")
    provider: str = Field(..., description="Provider identifier (e.g. google)")
    status: ConnectionStatus = Field(..., description="Current connection lifecycle status")
    scopes: list[str] = Field(default_factory=list, description="Granted scopes")
    account_email: str | None = Field(default=None, description="Connected account email preview")
    token_type: str = Field(default="Bearer", description="HTTP token type")
    expires_at: datetime | None = Field(default=None, description="Access token expiration timestamp")
    created_at: datetime = Field(..., description="Connection record creation timestamp")
    updated_at: datetime = Field(..., description="Connection record last updated timestamp")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Non-secret provider metadata")


class OAuthAuthorizationInitiate(BaseModel):
    """Payload sent by client when initiating an OAuth authorization flow."""

    provider: str = Field(default="google", description="Target integration provider")
    redirect_uri: str | None = Field(default=None, description="Callback redirect URI")
    scopes: list[str] = Field(default_factory=list, description="Optional custom scopes")


class OAuthAuthorizationRequest(BaseModel):
    """Payload returned when initiating an OAuth flow."""

    provider: str = Field(..., description="Target integration provider")
    authorization_url: str = Field(..., description="Provider authorization URL to open in browser")
    state: str = Field(..., description="Cryptographically random anti-forgery state")
    code_verifier: str | None = Field(
        default=None,
        description="PKCE code verifier (kept on client or secure state store)",
    )
    expires_at: datetime = Field(..., description="State expiration timestamp")


class OAuthCallbackResult(BaseModel):
    """Result returned after processing an OAuth redirect callback."""

    provider: str = Field(..., description="Target integration provider")
    status: ConnectionStatus = Field(..., description="Resulting connection status")
    account_email: str | None = Field(default=None, description="Connected account identifier")
    granted_scopes: list[str] = Field(default_factory=list, description="List of authorized scopes")
    error: str | None = Field(default=None, description="Error message if callback failed")


class CredentialStore(Protocol):
    """Abstract interface for local or hosted integration credential persistence."""

    def get_credential(self, service: str) -> str | None:
        """Retrieve token or secret for service."""
        ...

    def set_credential(self, service: str, secret: str) -> None:
        """Store token or secret for service."""
        ...

    def delete_credential(self, service: str) -> bool:
        """Delete stored credential for service."""
        ...
