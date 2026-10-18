"""Real-time SSE execution streaming and lifecycle management routes for agent runs."""

import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from icarus_contracts import (
    MessageCreate,
    MessageRole,
    PromptMessage,
    RunCancelResponse,
    RunCreate,
    RunCreateRequest,
    RunResponse,
    RunStatus,
    SSEEventPayload,
    TenantIdentity,
)
from icarus_core.agent.approvals import ApprovalEngine, ApprovalPolicy
from icarus_core.agent.loop import AgentLoop
from icarus_core.persistence import (
    TenantMessageRepository,
    TenantRunRepository,
    TenantSessionRepository,
)
from icarus_core.providers import ProviderRegistry

from icarus_api.auth import get_current_tenant, get_settings
from icarus_api.config import ApiSettings
from icarus_api.dependencies import (
    get_active_run_registry,
    get_provider_registry,
    get_tenant_message_repository,
    get_tenant_run_repository,
    get_tenant_session_repository,
)
from icarus_api.observer import SSEAgentObserver
from icarus_api.run_registry import ActiveRunRegistry

router = APIRouter(tags=["runs"])


@router.post("/v1/sessions/{session_id}/runs/stream")
async def stream_session_run(
    session_id: str,
    identity: Annotated[TenantIdentity, Depends(get_current_tenant)],
    session_repo: Annotated[TenantSessionRepository, Depends(get_tenant_session_repository)],
    msg_repo: Annotated[TenantMessageRepository, Depends(get_tenant_message_repository)],
    run_repo: Annotated[TenantRunRepository, Depends(get_tenant_run_repository)],
    run_registry: Annotated[ActiveRunRegistry, Depends(get_active_run_registry)],
    provider_registry: Annotated[ProviderRegistry, Depends(get_provider_registry)],
    settings: Annotated[ApiSettings, Depends(get_settings)],
    body: RunCreateRequest | None = None,
) -> StreamingResponse:
    """Execute an agent loop run in the background and stream real-time Server-Sent Events."""
    req = body or RunCreateRequest()

    # 1. Enforce session exists and belongs to authenticated tenant
    session = session_repo.get_session(session_id)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session '{session_id}' not found",
        )

    # 2. Append incoming user prompt if provided
    if req.prompt:
        msg_repo.create_message(
            MessageCreate(
                session_id=session_id,
                owner_id=identity.owner_id,
                role=MessageRole.USER,
                content=req.prompt,
            )
        )

    # 3. Create persistent run entry in running status
    effective_provider = req.provider or getattr(settings, "default_provider", "mock")
    effective_model = req.model or getattr(settings, "default_model", None)
    run_dto = run_repo.create_run(
        RunCreate(
            session_id=session_id,
            owner_id=identity.owner_id,
            provider=effective_provider,
            model=effective_model,
            status=RunStatus.RUNNING,
        )
    )
    run_id = run_dto.id

    # 4. Gather existing conversation messages
    db_messages = msg_repo.list_messages(session_id)
    prompt_messages = [m.to_prompt_message() for m in db_messages]

    # 5. Initialize provider adapter
    try:
        provider = provider_registry.get_provider(effective_provider)
    except Exception as exc:
        run_repo.update_run(
            run_id,
            status=RunStatus.FAILED,
            error_category=exc.__class__.__name__,
            completed=True,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to initialize provider '{effective_provider}': {exc}",
        ) from exc

    # 6. Configure approval engine
    approval_engine = (
        ApprovalEngine(policy=ApprovalPolicy.AUTO_APPROVE)
        if req.auto_approve
        else ApprovalEngine(policy=ApprovalPolicy.DENY)
    )

    # 7. Callback for recording intermediate agent messages to persistent transcript
    def on_run_message(msg: PromptMessage) -> None:
        msg_repo.create_message(
            MessageCreate(
                session_id=session_id,
                owner_id=identity.owner_id,
                role=msg.role,
                content=msg.content or "",
                tool_calls=msg.tool_calls,
                tool_call_id=msg.tool_call_id,
                name=msg.name,
            )
        )

    # 8. Setup agent loop, event queue, and observer
    agent_loop = AgentLoop(
        provider=provider,
        approval_engine=approval_engine,
        model=effective_model,
        temperature=req.temperature if req.temperature is not None else 0.7,
        max_turns=req.max_turns if req.max_turns is not None else 25,
        max_total_tokens=req.max_total_tokens,
        auto_compact=req.auto_compact,
        inject_system=True,
        message_callback=on_run_message,
    )

    queue: asyncio.Queue[SSEEventPayload | None] = asyncio.Queue()
    observer = SSEAgentObserver(queue, run_id=run_id)
    # Immediately emit initial turn_start so client connects and learns
    # run_id without provider latency
    queue.put_nowait(SSEEventPayload.turn_start(turn=1, run_id=run_id))

    # 9. Asynchronous background execution task
    async def _execute_loop() -> None:
        try:
            loop_result = await agent_loop.run(
                messages=prompt_messages,
                observer=observer,
            )
            if loop_result.finish_reason == "cancelled":
                run_repo.update_run(
                    run_id,
                    status=RunStatus.CANCELLED,
                    completed=True,
                    budget_counters=loop_result.budget_counters,
                )
                await queue.put(
                    SSEEventPayload.run_cancelled(
                        run_id=run_id,
                        message="Run cancelled",
                        budget_counters=loop_result.budget_counters,
                    )
                )
            else:
                run_repo.update_run(
                    run_id,
                    status=RunStatus.SUCCEEDED,
                    completed=True,
                    budget_counters=loop_result.budget_counters,
                )
                await queue.put(
                    SSEEventPayload.run_completed(
                        run_id=run_id,
                        result=loop_result.content,
                        budget_counters=loop_result.budget_counters,
                    )
                )
        except (asyncio.CancelledError, KeyboardInterrupt):
            run_repo.update_run(
                run_id,
                status=RunStatus.CANCELLED,
                completed=True,
            )
            await queue.put(
                SSEEventPayload.run_cancelled(
                    run_id=run_id,
                    message="Run cancelled mid-flight",
                )
            )
        except Exception as exc:
            run_repo.update_run(
                run_id,
                status=RunStatus.FAILED,
                error_category=exc.__class__.__name__,
                completed=True,
            )
            await queue.put(
                SSEEventPayload.run_failed(
                    run_id=run_id,
                    error=str(exc),
                    error_category=exc.__class__.__name__,
                )
            )
        finally:
            await queue.put(None)

    loop_task = asyncio.create_task(_execute_loop())
    await run_registry.register(run_id=run_id, owner_id=identity.owner_id, task=loop_task)

    # 10. Streaming generator yielding SSE messages
    async def event_generator():
        try:
            while True:
                payload = await queue.get()
                if payload is None:
                    break
                yield payload.to_sse_message()
        finally:
            await run_registry.unregister(run_id)
            if not loop_task.done():
                loop_task.cancel()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/v1/runs/{run_id}/cancel", response_model=RunCancelResponse)
async def cancel_run(
    run_id: str,
    identity: Annotated[TenantIdentity, Depends(get_current_tenant)],
    run_repo: Annotated[TenantRunRepository, Depends(get_tenant_run_repository)],
    run_registry: Annotated[ActiveRunRegistry, Depends(get_active_run_registry)],
) -> RunCancelResponse:
    """Signal cancellation to an active or queued run without corrupting state."""
    # 1. Check if run is actively executing in memory
    active = await run_registry.get(run_id, owner_id=identity.owner_id)
    if active is not None:
        await run_registry.cancel(run_id, owner_id=identity.owner_id)
        run_repo.update_run(run_id, status=RunStatus.CANCELLED, completed=True)
        return RunCancelResponse(
            run_id=run_id,
            status=RunStatus.CANCELLED,
            cancelled=True,
            message="Active run cancelled successfully.",
        )

    # 2. Check persistent run record
    run_dto = run_repo.get_run(run_id)
    if run_dto is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Run '{run_id}' not found",
        )

    if run_dto.status in (RunStatus.SUCCEEDED, RunStatus.FAILED, RunStatus.CANCELLED):
        return RunCancelResponse(
            run_id=run_id,
            status=run_dto.status,
            cancelled=False,
            message=f"Run is already {run_dto.status}.",
        )

    # If queued or running in DB but not active in memory
    run_repo.update_run(run_id, status=RunStatus.CANCELLED, completed=True)
    return RunCancelResponse(
        run_id=run_id,
        status=RunStatus.CANCELLED,
        cancelled=True,
        message="Run cancelled.",
    )


@router.get("/v1/runs/{run_id}", response_model=RunResponse)
async def get_run(
    run_id: str,
    run_repo: Annotated[TenantRunRepository, Depends(get_tenant_run_repository)],
) -> RunResponse:
    """Retrieve detailed state and metrics for a specific agent run."""
    run = run_repo.get_run(run_id)
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Run '{run_id}' not found",
        )
    return RunResponse(**run.model_dump())


@router.get("/v1/sessions/{session_id}/runs", response_model=list[RunResponse])
async def list_session_runs(
    session_id: str,
    session_repo: Annotated[TenantSessionRepository, Depends(get_tenant_session_repository)],
    run_repo: Annotated[TenantRunRepository, Depends(get_tenant_run_repository)],
) -> list[RunResponse]:
    """Retrieve all historical execution runs associated with a tenant session."""
    session = session_repo.get_session(session_id)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session '{session_id}' not found",
        )
    runs = run_repo.list_runs_for_session(session_id)
    return [RunResponse(**r.model_dump()) for r in runs]
