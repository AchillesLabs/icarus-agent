"""Security tests for CredentialVault fail-closed behavior, key rotation, and secret redaction."""

import json
from unittest.mock import patch

import pytest
from icarus_core.security.vault import (
    CredentialVault,
    MissingMasterKeyError,
    mask_secret,
    redact_secret,
    rotate_secret,
)
from icarus_core.tools.auth import (
    ToolAuthManager,
    get_credentials_file,
    get_legacy_credentials_file,
    load_stored_credentials,
    save_stored_credentials,
)


def test_missing_master_key_fails_closed():
    """In production without ICARUS_VAULT_MASTER_KEY or explicit key, vault must fail closed."""
    with patch.dict("os.environ", {}, clear=True):
        with pytest.raises(MissingMasterKeyError, match="No encryption master key provided"):
            CredentialVault(allow_insecure_dev_key=False)


def test_key_rotation_and_rekey():
    """Key rotation decrypts with old vault and re-encrypts with new vault cleanly."""
    vault_old = CredentialVault(master_key="old-master-secret-key-1111")
    vault_new = CredentialVault(master_key="new-master-secret-key-2222")

    secret_value = "sk-live-super-confidential-api-token"
    old_ciphertext = vault_old.encrypt(secret_value)

    # Cannot decrypt old ciphertext with new vault directly
    with pytest.raises(Exception):
        vault_new.decrypt(old_ciphertext)

    # Rotate secret
    new_ciphertext = rotate_secret(old_ciphertext, vault_old, vault_new)
    assert new_ciphertext != old_ciphertext

    # Decrypt with new vault succeeds
    assert vault_new.decrypt(new_ciphertext) == secret_value


def test_secret_masking():
    """Secret masking produces safe preview hints and never exposes plaintext."""
    assert mask_secret("sk-1234567890abcdef") == "sk-...cdef"
    assert mask_secret("short") == "***"
    assert mask_secret("") == ""


def test_redact_secret_recursive():
    """Recursive secret redaction strips sensitive tokens from strings, dicts, lists."""
    secret = "sk-super-secret-production-key-999"
    payload = {
        "error": f"Failed calling provider with key {secret}",
        "metadata": [
            f"token={secret}",
            {"nested_secret": secret},
        ],
        "safe_field": "hello world",
    }

    redacted = redact_secret(payload, secret)
    assert secret not in str(redacted)
    assert "[REDACTED]" in redacted["error"]
    assert "[REDACTED]" in redacted["metadata"][0]
    assert redacted["metadata"][1]["nested_secret"] == "[REDACTED]"
    assert redacted["safe_field"] == "hello world"


def test_tool_auth_manager_encrypts_on_disk(tmp_path, monkeypatch):
    """Tool credentials stored on disk must be encrypted and not plaintext JSON."""
    monkeypatch.setenv("ICARUS_HOME", str(tmp_path))

    ToolAuthManager.save_token("test_service", "my-super-secret-token-xyz")

    enc_file = get_credentials_file()
    assert enc_file.exists()

    # The file content must NOT contain the plaintext token
    raw_content = enc_file.read_bytes()
    assert b"my-super-secret-token-xyz" not in raw_content

    # Loading through ToolAuthManager succeeds and returns the secret
    assert ToolAuthManager.get_token("test_service") == "my-super-secret-token-xyz"


def test_tool_auth_manager_migrates_legacy_plaintext_file(tmp_path, monkeypatch):
    """Legacy plaintext credentials.json is automatically encrypted into credentials.enc."""
    monkeypatch.setenv("ICARUS_HOME", str(tmp_path))

    legacy_file = get_legacy_credentials_file()
    legacy_file.parent.mkdir(parents=True, exist_ok=True)
    legacy_file.write_text(json.dumps({"github": "ghp_legacyPlaintextToken123"}), encoding="utf-8")

    # Before migration, enc file does not exist
    enc_file = get_credentials_file()
    assert not enc_file.exists()

    # Load triggers migration
    creds = load_stored_credentials()
    assert creds.get("github") == "ghp_legacyPlaintextToken123"

    # Encrypted file is created
    assert enc_file.exists()
    assert b"ghp_legacyPlaintextToken123" not in enc_file.read_bytes()

    # Legacy file was scrubbed
    assert "ghp_legacyPlaintextToken123" not in legacy_file.read_text(encoding="utf-8")
