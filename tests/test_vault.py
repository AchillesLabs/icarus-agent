"""Comprehensive tests for server-side credential vault, secret encryption at rest,

key masking, and tenant-isolated BYOK management.
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from icarus_api.app import create_app
from icarus_api.config import ApiSettings
from icarus_contracts.vault import VaultCredentialResponse
from icarus_core.persistence.database import DatabaseManager
from icarus_core.persistence.models import Base, TenantCredentialModel
from icarus_core.persistence.repository import CredentialRepository, TenantCredentialRepository
from icarus_core.security import CredentialVault, VaultDecryptionError, mask_secret
from sqlalchemy import select


@pytest.fixture
def test_db_manager() -> DatabaseManager:
    """Provide a fresh in-memory SQLite database initialized with all tables."""
    db_manager = DatabaseManager(db_url="sqlite:///:memory:")
    Base.metadata.create_all(db_manager.engine)
    return db_manager


def test_mask_secret_helper():
    assert mask_secret("") == ""
    assert mask_secret("short") == "***"
    assert mask_secret("12345678") == "***"
    assert mask_secret("sk-or-v1-abcdef12345678904a2b") == "sk-...4a2b"
    assert mask_secret("sk-ant-api03-abcdef1234567890") == "sk-...7890"
    assert mask_secret("gsk_1234567890abcdef") == "gsk...cdef"


def test_credential_vault_encryption_decryption_and_tampering():
    vault = CredentialVault(master_key="test-master-secret-12345")
    secret = "sk-or-v1-super-secret-api-key-9999"

    # Encrypt
    ciphertext_1 = vault.encrypt(secret)
    ciphertext_2 = vault.encrypt(secret)

    assert ciphertext_1 != secret
    # Fernet generates fresh IV/nonce on each encryption call
    assert ciphertext_1 != ciphertext_2

    # Decrypt
    decrypted = vault.decrypt(ciphertext_1)
    assert decrypted == secret
    assert vault.decrypt(ciphertext_2) == secret

    # Tampering with ciphertext raises VaultDecryptionError
    tampered = ciphertext_1[:-4] + "AAAA"
    with pytest.raises(VaultDecryptionError):
        vault.decrypt(tampered)

    # Decrypting with wrong master key raises VaultDecryptionError
    other_vault = CredentialVault(master_key="different-master-secret-99999")
    with pytest.raises(VaultDecryptionError):
        other_vault.decrypt(ciphertext_1)


def test_tenant_credential_repository_crud_and_encryption_at_rest(test_db_manager: DatabaseManager):
    vault = CredentialVault(master_key="repo-test-master-key")
    cred_repo = CredentialRepository(test_db_manager, vault=vault)
    tenant_repo = TenantCredentialRepository(test_db_manager, owner_id="tenant-alpha", vault=vault)

    raw_secret = "sk-ant-api03-abcdef1234567890"

    # 1. Set credential
    saved = tenant_repo.set_credential("anthropic", raw_secret)
    assert isinstance(saved, VaultCredentialResponse)
    assert saved.provider == "anthropic"
    assert saved.key_hint == "sk-...7890"

    # 2. Inspect raw database row to prove encryption at rest
    with test_db_manager.session_scope() as session:
        stmt = select(TenantCredentialModel).where(
            TenantCredentialModel.owner_id == "tenant-alpha",
            TenantCredentialModel.provider == "anthropic",
        )
        model = session.execute(stmt).scalar_one_or_none()
        assert model is not None
        assert model.encrypted_secret != raw_secret
        assert raw_secret not in model.encrypted_secret
        assert model.key_hint == "sk-...7890"

    # 3. Retrieve masked credential
    retrieved = tenant_repo.get_credential("anthropic")
    assert retrieved is not None
    assert retrieved.provider == "anthropic"
    assert retrieved.key_hint == "sk-...7890"

    # 4. Retrieve decrypted plaintext secret
    decrypted_secret = tenant_repo.get_decrypted_secret("anthropic")
    assert decrypted_secret == raw_secret
    assert cred_repo.get_decrypted_secret("tenant-alpha", "anthropic") == raw_secret

    # 5. Upsert credential for same provider updates in place
    updated_secret = "sk-ant-api03-updated-secret-9999"
    updated = tenant_repo.set_credential("anthropic", updated_secret)
    assert updated.key_hint == "sk-...9999"
    assert tenant_repo.get_decrypted_secret("anthropic") == updated_secret

    # 6. List credentials
    tenant_repo.set_credential("groq", "gsk_1234567890abcdef")
    creds = tenant_repo.list_credentials()
    assert len(creds) == 2
    providers = [c.provider for c in creds]
    assert providers == ["anthropic", "groq"]

    # 7. Delete credential
    assert tenant_repo.delete_credential("anthropic") is True
    assert tenant_repo.get_credential("anthropic") is None
    assert tenant_repo.delete_credential("anthropic") is False
    assert len(tenant_repo.list_credentials()) == 1


@pytest.mark.asyncio
async def test_api_vault_endpoints_lifecycle(test_db_manager: DatabaseManager):
    settings = ApiSettings(auth_tokens={"user-token": "org-acme"})
    vault = CredentialVault(master_key="api-vault-test-key")
    app = create_app(settings=settings, db_manager=test_db_manager, credential_vault=vault)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Unauthenticated request rejected with 401
        unauth = await client.get("/v1/vault/credentials")
        assert unauth.status_code == 401

        # 2. Add Groq credential
        create_resp = await client.post(
            "/v1/vault/credentials",
            json={"provider": "groq", "api_key": "gsk_testapikey1234567890abc"},
            headers={"Authorization": "Bearer user-token"},
        )
        assert create_resp.status_code == 201
        data = create_resp.json()
        assert data["provider"] == "groq"
        assert data["key_hint"] == "gsk...0abc"
        # Invariant: plaintext secret is never returned in response body
        assert "api_key" not in data
        assert "secret" not in data

        # 3. Add OpenRouter credential
        await client.post(
            "/v1/vault/credentials",
            json={"provider": "openrouter", "api_key": "sk-or-v1-abcdef1234567890xyz9"},
            headers={"Authorization": "Bearer user-token"},
        )

        # 4. List credentials
        list_resp = await client.get(
            "/v1/vault/credentials",
            headers={"Authorization": "Bearer user-token"},
        )
        assert list_resp.status_code == 200
        creds = list_resp.json()
        assert len(creds) == 2
        hints = {c["provider"]: c["key_hint"] for c in creds}
        assert hints == {"groq": "gsk...0abc", "openrouter": "sk-...xyz9"}

        # 5. Delete credential
        del_resp = await client.delete(
            "/v1/vault/credentials/groq",
            headers={"Authorization": "Bearer user-token"},
        )
        assert del_resp.status_code == 200
        assert del_resp.json() == {"provider": "groq", "deleted": True}

        # 6. Delete again returns 404
        del_again = await client.delete(
            "/v1/vault/credentials/groq",
            headers={"Authorization": "Bearer user-token"},
        )
        assert del_again.status_code == 404


@pytest.mark.asyncio
async def test_cross_tenant_vault_isolation(test_db_manager: DatabaseManager):
    settings = ApiSettings(
        auth_tokens={
            "alice-token": "tenant-alice",
            "bob-token": "tenant-bob",
        }
    )
    vault = CredentialVault(master_key="isolation-test-key")
    app = create_app(settings=settings, db_manager=test_db_manager, credential_vault=vault)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Alice registers Anthropic key
        alice_create = await client.post(
            "/v1/vault/credentials",
            json={"provider": "anthropic", "api_key": "sk-ant-api03-alicekey12345"},
            headers={"Authorization": "Bearer alice-token"},
        )
        assert alice_create.status_code == 201

        # Bob registers OpenRouter key
        bob_create = await client.post(
            "/v1/vault/credentials",
            json={"provider": "openrouter", "api_key": "sk-or-v1-bobkey12345"},
            headers={"Authorization": "Bearer bob-token"},
        )
        assert bob_create.status_code == 201

        # Alice listing credentials only sees Anthropic
        alice_list = await client.get(
            "/v1/vault/credentials",
            headers={"Authorization": "Bearer alice-token"},
        )
        assert alice_list.status_code == 200
        alice_creds = alice_list.json()
        assert len(alice_creds) == 1
        assert alice_creds[0]["provider"] == "anthropic"

        # Bob listing credentials only sees OpenRouter
        bob_list = await client.get(
            "/v1/vault/credentials",
            headers={"Authorization": "Bearer bob-token"},
        )
        assert bob_list.status_code == 200
        bob_creds = bob_list.json()
        assert len(bob_creds) == 1
        assert bob_creds[0]["provider"] == "openrouter"

        # Bob attempts to delete Alice's Anthropic credential -> 404
        bob_del_alice = await client.delete(
            "/v1/vault/credentials/anthropic",
            headers={"Authorization": "Bearer bob-token"},
        )
        assert bob_del_alice.status_code == 404

        # Alice's credential remains intact
        alice_check = await client.get(
            "/v1/vault/credentials",
            headers={"Authorization": "Bearer alice-token"},
        )
        assert len(alice_check.json()) == 1
