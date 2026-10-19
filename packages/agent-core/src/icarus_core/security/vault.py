"""Symmetric credential vault and secret masking utilities for server-side BYOK management."""

from __future__ import annotations

import base64
import hashlib
import os

from cryptography.fernet import Fernet, InvalidToken

DEFAULT_DEV_VAULT_KEY = "icarus-insecure-dev-master-vault-key-32b"


class VaultDecryptionError(Exception):
    """Raised when decrypting a vault secret fails due to tampering or invalid master key."""


def mask_secret(secret: str) -> str:
    """Format an API secret safely into a preview hint (e.g. 'sk-...4a2b').

    If the secret is very short, returns '***'.
    """
    if not secret:
        return ""
    if len(secret) <= 8:
        return "***"
    return f"{secret[:3]}...{secret[-4:]}"


class CredentialVault:
    """Authenticated symmetric encryption vault backed by AES-128-CBC + HMAC-SHA256 (Fernet)

    derived from a dedicated master secret key.
    """

    def __init__(self, master_key: str | bytes | None = None) -> None:
        raw_key = master_key or os.environ.get("ICARUS_VAULT_MASTER_KEY") or DEFAULT_DEV_VAULT_KEY
        raw_bytes = raw_key.encode("utf-8") if isinstance(raw_key, str) else raw_key

        # Derive deterministic 32-byte urlsafe-base64 key suitable for Fernet
        derived_key = base64.urlsafe_b64encode(hashlib.sha256(raw_bytes).digest())
        self._fernet = Fernet(derived_key)

    def encrypt(self, secret: str) -> str:
        """Encrypt plaintext secret into authenticated ciphertext string."""
        if not isinstance(secret, str):
            raise TypeError("Secret must be a string")
        encrypted_bytes = self._fernet.encrypt(secret.encode("utf-8"))
        return encrypted_bytes.decode("utf-8")

    def decrypt(self, ciphertext: str) -> str:
        """Decrypt ciphertext into plaintext string, verifying HMAC authenticity."""
        if not isinstance(ciphertext, str):
            raise TypeError("Ciphertext must be a string")
        try:
            decrypted_bytes = self._fernet.decrypt(ciphertext.encode("utf-8"))
            return decrypted_bytes.decode("utf-8")
        except (InvalidToken, Exception) as exc:
            raise VaultDecryptionError(
                "Failed to decrypt vault secret: invalid token or tampering detected"
            ) from exc

    def mask(self, secret: str) -> str:
        """Convenience method delegating to mask_secret."""
        return mask_secret(secret)
