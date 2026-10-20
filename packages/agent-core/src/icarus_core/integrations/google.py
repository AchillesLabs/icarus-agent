"""Google OAuth 2.0 / PKCE client and Google REST API integration client."""

from __future__ import annotations

import os
from typing import Any
from urllib.parse import urlencode

import httpx
from icarus_contracts.integrations import AuthMethod, IntegrationManifest

from icarus_core.integrations.pkce import (
    generate_code_challenge,
    generate_code_verifier,
    generate_oauth_state,
)

# Standard Google OAuth 2.0 endpoints
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_REVOKE_URL = "https://oauth2.googleapis.com/revoke"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"

# Scopes
GOOGLE_SCOPE_USERINFO_EMAIL = "https://www.googleapis.com/auth/userinfo.email"
GOOGLE_SCOPE_CALENDAR_READ = "https://www.googleapis.com/auth/calendar.readonly"
GOOGLE_SCOPE_CALENDAR_EVENTS = "https://www.googleapis.com/auth/calendar.events"
GOOGLE_SCOPE_GMAIL_READ = "https://www.googleapis.com/auth/gmail.readonly"
GOOGLE_SCOPE_GMAIL_COMPOSE = "https://www.googleapis.com/auth/gmail.compose"
GOOGLE_SCOPE_GMAIL_SEND = "https://www.googleapis.com/auth/gmail.send"
GOOGLE_SCOPE_DRIVE_READ = "https://www.googleapis.com/auth/drive.readonly"

DEFAULT_GOOGLE_SCOPES = [
    GOOGLE_SCOPE_USERINFO_EMAIL,
    GOOGLE_SCOPE_CALENDAR_READ,
    GOOGLE_SCOPE_CALENDAR_EVENTS,
    GOOGLE_SCOPE_GMAIL_READ,
    GOOGLE_SCOPE_GMAIL_COMPOSE,
    GOOGLE_SCOPE_DRIVE_READ,
]

GOOGLE_MANIFEST = IntegrationManifest(
    id="google",
    display_name="Google Workspace (Gmail, Calendar, Drive)",
    description="Secure first-party OAuth 2.0 PKCE integration for Google Calendar, Gmail, and Google Drive.",
    auth_method=AuthMethod.OAUTH2_PKCE,
    required_scopes=DEFAULT_GOOGLE_SCOPES,
    tools=[
        "gmail_search",
        "gmail_send",
        "calendar_events",
        "calendar_create_event",
        "drive_search",
        "drive_read_file",
    ],
    required_config=["GOOGLE_CLIENT_ID"],
    supported_modes=["local", "hosted"],
)


class GoogleOAuthError(Exception):
    """Raised when Google OAuth exchange, refresh, or API call fails."""


class GoogleOAuthClient:
    """Manages Google OAuth 2.0 authorization URL creation, PKCE, token exchange, and token refresh."""

    def __init__(
        self,
        client_id: str | None = None,
        client_secret: str | None = None,
        http_client: httpx.Client | None = None,
    ) -> None:
        self.client_id = client_id or os.getenv("GOOGLE_CLIENT_ID") or ""
        self.client_secret = client_secret or os.getenv("GOOGLE_CLIENT_SECRET") or ""
        self._http_client = http_client

    def is_configured(self) -> bool:
        """Return True if Google client credentials are configured."""
        return bool(self.client_id.strip())

    def create_authorization_flow(
        self,
        redirect_uri: str,
        scopes: list[str] | None = None,
        state: str | None = None,
    ) -> tuple[str, str, str]:
        """Create a complete PKCE authorization request.

        Returns: (authorization_url, state, code_verifier)
        """
        if not self.is_configured():
            raise GoogleOAuthError(
                "Google OAuth is not configured. Operator must set the GOOGLE_CLIENT_ID "
                "environment variable or register OAuth credentials in the Google Cloud Console."
            )

        active_state = state or generate_oauth_state()
        code_verifier = generate_code_verifier(64)
        code_challenge = generate_code_challenge(code_verifier)
        requested_scopes = " ".join(scopes or DEFAULT_GOOGLE_SCOPES)

        params = {
            "client_id": self.client_id,
            "response_type": "code",
            "redirect_uri": redirect_uri,
            "scope": requested_scopes,
            "state": active_state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "access_type": "offline",
            "prompt": "consent",
        }

        auth_url = f"{GOOGLE_AUTH_URL}?{urlencode(params)}"
        return auth_url, active_state, code_verifier

    def exchange_code(
        self,
        code: str,
        redirect_uri: str,
        code_verifier: str,
    ) -> dict[str, Any]:
        """Exchange authorization code with Google token endpoint using PKCE verifier."""
        if not self.is_configured():
            raise GoogleOAuthError("GOOGLE_CLIENT_ID is not configured.")

        payload: dict[str, str] = {
            "grant_type": "authorization_code",
            "client_id": self.client_id,
            "code": code,
            "redirect_uri": redirect_uri,
            "code_verifier": code_verifier,
        }
        if self.client_secret:
            payload["client_secret"] = self.client_secret

        try:
            client = self._http_client or httpx.Client(timeout=15.0)
            should_close = self._http_client is None
            try:
                resp = client.post(
                    GOOGLE_TOKEN_URL,
                    data=payload,
                    headers={"Accept": "application/json"},
                )
                data = resp.json()
                if resp.status_code != 200:
                    err_msg = data.get("error_description") or data.get("error") or resp.text
                    raise GoogleOAuthError(f"Google token exchange failed ({resp.status_code}): {err_msg}")
                return data
            finally:
                if should_close:
                    client.close()
        except GoogleOAuthError:
            raise
        except Exception as exc:
            raise GoogleOAuthError(f"Network error during Google token exchange: {exc}") from exc

    def refresh_access_token(self, refresh_token: str) -> dict[str, Any]:
        """Refresh an expired access token using the stored refresh token."""
        if not self.is_configured():
            raise GoogleOAuthError("GOOGLE_CLIENT_ID is not configured.")

        payload: dict[str, str] = {
            "grant_type": "refresh_token",
            "client_id": self.client_id,
            "refresh_token": refresh_token,
        }
        if self.client_secret:
            payload["client_secret"] = self.client_secret

        try:
            client = self._http_client or httpx.Client(timeout=15.0)
            should_close = self._http_client is None
            try:
                resp = client.post(
                    GOOGLE_TOKEN_URL,
                    data=payload,
                    headers={"Accept": "application/json"},
                )
                data = resp.json()
                if resp.status_code != 200:
                    err_msg = data.get("error_description") or data.get("error") or resp.text
                    raise GoogleOAuthError(f"Google token refresh failed ({resp.status_code}): {err_msg}")
                return data
            finally:
                if should_close:
                    client.close()
        except GoogleOAuthError:
            raise
        except Exception as exc:
            raise GoogleOAuthError(f"Network error during Google token refresh: {exc}") from exc

    def revoke_token(self, token: str) -> bool:
        """Call Google token revocation endpoint to disconnect account."""
        try:
            client = self._http_client or httpx.Client(timeout=10.0)
            should_close = self._http_client is None
            try:
                resp = client.post(
                    GOOGLE_REVOKE_URL,
                    params={"token": token},
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
                return resp.status_code == 200
            finally:
                if should_close:
                    client.close()
        except Exception:
            return False

    def get_account_email(self, access_token: str) -> str | None:
        """Fetch the authorized account's email address using the userinfo endpoint."""
        try:
            client = self._http_client or httpx.Client(timeout=10.0)
            should_close = self._http_client is None
            try:
                resp = client.get(
                    GOOGLE_USERINFO_URL,
                    headers={"Authorization": f"Bearer {access_token}"},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    return data.get("email")
            finally:
                if should_close:
                    client.close()
        except Exception:
            pass
        return None
