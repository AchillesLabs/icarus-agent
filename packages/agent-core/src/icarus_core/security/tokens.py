"""Cryptographic primitives for dynamic API token generation, hashing, and verification."""

from __future__ import annotations

import hashlib
import secrets

DEFAULT_TOKEN_PREFIX = "sk_icarus_"


def hash_api_token(token: str) -> str:
    """Compute the SHA-256 hex digest of a raw token string."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def generate_api_token(prefix: str = DEFAULT_TOKEN_PREFIX) -> tuple[str, str, str]:
    """Generate a new cryptographically random API token, a masked prefix, and SHA-256 hash.

    Returns:
        tuple[str, str, str]: (raw_token, display_prefix, token_hash)
    """
    random_secret = secrets.token_urlsafe(32)
    raw_token = f"{prefix}{random_secret}"
    display_prefix = f"{raw_token[:13]}...{raw_token[-4:]}"
    token_hash = hash_api_token(raw_token)
    return raw_token, display_prefix, token_hash


def verify_token_hash(candidate_token: str, expected_hash: str) -> bool:
    """Verify that a candidate token matches the expected SHA-256 hash in constant time."""
    candidate_hash = hash_api_token(candidate_token)
    return secrets.compare_digest(candidate_hash, expected_hash)
