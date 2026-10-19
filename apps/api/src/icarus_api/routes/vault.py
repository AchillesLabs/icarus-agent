"""FastAPI routes for tenant-isolated server-side credential vault and BYOK management."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from icarus_contracts.vault import (
    VaultCredentialCreate,
    VaultCredentialDeleteResponse,
    VaultCredentialResponse,
)
from icarus_core.persistence import TenantCredentialRepository

from icarus_api.dependencies import get_tenant_credential_repository

router = APIRouter(prefix="/v1/vault/credentials", tags=["Vault"])


@router.post(
    "",
    response_model=VaultCredentialResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register or update an encrypted BYOK provider credential",
)
async def set_vault_credential(
    body: VaultCredentialCreate,
    repo: Annotated[TenantCredentialRepository, Depends(get_tenant_credential_repository)],
    request: Request,
) -> VaultCredentialResponse:
    """Encrypt and securely persist a model provider API key for the authenticated tenant."""
    res = repo.set_credential(provider=body.provider, secret=body.api_key)
    audit_logger = getattr(request.app.state, "audit_logger", None)
    if audit_logger:
        audit_logger.log_vault_credential_stored(
            actor_id=repo.owner_id,
            provider=body.provider,
            key_hint=res.key_hint,
            client_ip=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    return res


@router.get(
    "",
    response_model=list[VaultCredentialResponse],
    status_code=status.HTTP_200_OK,
    summary="List configured provider credentials with masked previews",
)
async def list_vault_credentials(
    repo: Annotated[TenantCredentialRepository, Depends(get_tenant_credential_repository)],
) -> list[VaultCredentialResponse]:
    """Retrieve all configured model provider credentials for the authenticated tenant
    with masked previews.
    """
    return repo.list_credentials()


@router.delete(
    "/{provider}",
    response_model=VaultCredentialDeleteResponse,
    status_code=status.HTTP_200_OK,
    summary="Delete a stored provider credential from the vault",
)
async def delete_vault_credential(
    provider: str,
    repo: Annotated[TenantCredentialRepository, Depends(get_tenant_credential_repository)],
    request: Request,
) -> VaultCredentialDeleteResponse:
    """Remove a configured model provider credential belonging to the authenticated tenant."""
    deleted = repo.delete_credential(provider)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Credential for provider '{provider}' not found",
        )
    audit_logger = getattr(request.app.state, "audit_logger", None)
    if audit_logger:
        audit_logger.log_vault_credential_deleted(
            actor_id=repo.owner_id,
            provider=provider,
            client_ip=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    return VaultCredentialDeleteResponse(provider=provider, deleted=True)
