"""Cryptographic helpers for OAuth 2.0 PKCE (RFC 7636) and anti-forgery state generation."""

from __future__ import annotations

import base64
import hashlib
import secrets


def generate_code_verifier(length: int = 64) -> str:
    """Generate a high-entropy cryptographically random string using [A-Z, a-z, 0-9, -._~]."""
    if length < 43 or length > 128:
        raise ValueError("PKCE code verifier length must be between 43 and 128 characters.")
    return secrets.token_urlsafe(length)[:length]


def generate_code_challenge(verifier: str) -> str:
    """Generate SHA-256 base64url-encoded code challenge without padding (S256)."""
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return challenge


def generate_oauth_state(num_bytes: int = 32) -> str:
    """Generate a cryptographically random, unguessable OAuth anti-forgery state token."""
    return secrets.token_urlsafe(num_bytes)
