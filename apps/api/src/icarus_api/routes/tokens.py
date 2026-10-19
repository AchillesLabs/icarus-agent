"""FastAPI routes for dynamic API token issuance, listing, and instant revocation."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from icarus_contracts.tokens import (
    ApiTokenCreatedResponse,
    ApiTokenCreateRequest,
    ApiTokenResponse,
)
from icarus_core.persistence import TenantApiTokenRepository
from icarus_core.security import generate_api_token

from icarus_api.auth import TokenValidationCache
from icarus_api.dependencies import get_tenant_api_token_repository, get_token_cache

router = APIRouter(prefix="/v1/auth/tokens", tags=["Authentication"])


@router.post(
    "",
    response_model=ApiTokenCreatedResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Issue a new dynamic API access token",
)
async def create_api_token(
    body: ApiTokenCreateRequest,
    repo: Annotated[TenantApiTokenRepository, Depends(get_tenant_api_token_repository)],
) -> ApiTokenCreatedResponse:
    """Generate a new cryptographically random API token, hash and persist it,

    and return the plaintext secret exactly once.
    """
    raw_token, prefix, token_hash = generate_api_token()
    token_dto = repo.create_token(
        name=body.name,
        token_hash=token_hash,
        prefix=prefix,
        expires_at=body.expires_at,
    )
    return ApiTokenCreatedResponse(
        **token_dto.model_dump(),
        token=raw_token,
    )


@router.get(
    "",
    response_model=list[ApiTokenResponse],
    status_code=status.HTTP_200_OK,
    summary="List active and revoked API tokens for the authenticated tenant",
)
async def list_api_tokens(
    repo: Annotated[TenantApiTokenRepository, Depends(get_tenant_api_token_repository)],
    include_revoked: Annotated[
        bool, Query(description="Include revoked tokens in the returned list")
    ] = True,
) -> list[ApiTokenResponse]:
    """Retrieve all issued API tokens belonging to the authenticated tenant."""
    return repo.list_tokens(include_revoked=include_revoked)


@router.post(
    "/{token_id}/revoke",
    response_model=ApiTokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Instantly revoke an API token and purge it from cache",
)
async def revoke_api_token(
    token_id: str,
    repo: Annotated[TenantApiTokenRepository, Depends(get_tenant_api_token_repository)],
    token_cache: Annotated[TokenValidationCache, Depends(get_token_cache)],
) -> ApiTokenResponse:
    """Immediately mark an API token as revoked and purge it from in-memory validation caches."""
    token_dto = repo.revoke_token(token_id)
    if token_dto is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"API token '{token_id}' not found",
        )
    # Purge immediately from in-memory cache
    token_cache.invalidate_by_token_id(token_id)
    return token_dto
