"""RESTful routes for conversational session and message lifecycle management."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from icarus_contracts import (
    MessageCreate,
    MessageCreateRequest,
    MessageResponse,
    SessionCreate,
    SessionCreateRequest,
    SessionListResponse,
    SessionResponse,
)
from icarus_core.persistence import (
    TenantMessageRepository,
    TenantSessionRepository,
)

from icarus_api.dependencies import (
    get_tenant_message_repository,
    get_tenant_session_repository,
)

router = APIRouter(prefix="/v1/sessions", tags=["sessions"])


@router.get("", response_model=SessionListResponse)
async def list_sessions(
    repo: Annotated[TenantSessionRepository, Depends(get_tenant_session_repository)],
    limit: Annotated[int, Query(ge=1, le=100, description="Page limit")] = 50,
    offset: Annotated[int, Query(ge=0, description="Page offset")] = 0,
) -> SessionListResponse:
    """Retrieve paginated session summaries belonging to the authenticated tenant."""
    items = repo.list_session_summaries(limit=limit, offset=offset)
    total = repo.count_sessions()
    return SessionListResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("", response_model=SessionResponse, status_code=status.HTTP_201_CREATED)
async def create_session(
    repo: Annotated[TenantSessionRepository, Depends(get_tenant_session_repository)],
    body: SessionCreateRequest | None = None,
) -> SessionResponse:
    """Create a new conversational session bound to the authenticated tenant."""
    req = body or SessionCreateRequest()
    session_dto = repo.create_session(
        SessionCreate(
            title=req.title,
            mode=req.mode,
        )
    )
    return SessionResponse(**session_dto.model_dump())


@router.get("/{session_id}", response_model=SessionResponse)
async def get_session(
    session_id: str,
    repo: Annotated[TenantSessionRepository, Depends(get_tenant_session_repository)],
) -> SessionResponse:
    """Retrieve detailed session metadata and aggregated telemetry by ID."""
    summary = repo.get_session_summary(session_id)
    if summary is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session '{session_id}' not found",
        )
    return SessionResponse(**summary.model_dump())


@router.delete("/{session_id}")
async def delete_session(
    session_id: str,
    repo: Annotated[TenantSessionRepository, Depends(get_tenant_session_repository)],
) -> dict[str, str | bool]:
    """Permanently delete a session and cascade deletion to related messages and runs."""
    deleted = repo.delete_session(session_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session '{session_id}' not found",
        )
    return {"deleted": True, "id": session_id}


@router.get("/{session_id}/messages", response_model=list[MessageResponse])
async def list_session_messages(
    session_id: str,
    repo: Annotated[TenantSessionRepository, Depends(get_tenant_session_repository)],
    msg_repo: Annotated[TenantMessageRepository, Depends(get_tenant_message_repository)],
) -> list[MessageResponse]:
    """Retrieve the chronological message transcript for a tenant session."""
    session = repo.get_session(session_id)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session '{session_id}' not found",
        )
    messages = msg_repo.list_messages(session_id)
    return [MessageResponse(**msg.model_dump()) for msg in messages]


@router.post(
    "/{session_id}/messages",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_session_message(
    session_id: str,
    body: MessageCreateRequest,
    repo: Annotated[TenantSessionRepository, Depends(get_tenant_session_repository)],
    msg_repo: Annotated[TenantMessageRepository, Depends(get_tenant_message_repository)],
) -> MessageResponse:
    """Append a new message to an existing tenant conversation thread."""
    session = repo.get_session(session_id)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session '{session_id}' not found",
        )
    msg_dto = msg_repo.create_message(
        MessageCreate(
            session_id=session_id,
            role=body.role,
            content=body.content,
            tool_calls=body.tool_calls,
            tool_call_id=body.tool_call_id,
            name=body.name,
        )
    )
    return MessageResponse(**msg_dto.model_dump())
