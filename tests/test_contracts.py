"""Tests for domain contracts and DTOs in icarus_contracts."""

import uuid
from datetime import UTC, datetime

from icarus_contracts import (
    CredentialResult,
    CredentialSource,
    IcarusConfig,
    MessageDTO,
    MessageRole,
    RunDTO,
    RunStatus,
    SessionDTO,
    TokenUsage,
)


def test_message_role_enum_values():
    assert MessageRole.USER == "user"
    assert MessageRole.ASSISTANT == "assistant"
    assert MessageRole.SYSTEM == "system"
    assert MessageRole.TOOL == "tool"


def test_run_status_enum_values():
    assert RunStatus.QUEUED == "queued"
    assert RunStatus.RUNNING == "running"
    assert RunStatus.WAITING_FOR_APPROVAL == "waiting_for_approval"
    assert RunStatus.SUCCEEDED == "succeeded"
    assert RunStatus.FAILED == "failed"
    assert RunStatus.CANCELLED == "cancelled"
    assert RunStatus.EXPIRED == "expired"


def test_session_dto_creation_and_defaults():
    now = datetime.now(UTC)
    session_id = str(uuid.uuid4())
    dto = SessionDTO(
        id=session_id,
        owner_id="default",
        mode="chat",
        title="Test Session",
        created_at=now,
        updated_at=now,
        metadata_version=1,
    )
    assert dto.id == session_id
    assert dto.title == "Test Session"
    assert dto.mode == "chat"
    assert dto.metadata_version == 1


def test_message_dto_creation():
    now = datetime.now(UTC)
    msg_id = str(uuid.uuid4())
    sess_id = str(uuid.uuid4())
    msg = MessageDTO(
        id=msg_id,
        session_id=sess_id,
        owner_id="default",
        role=MessageRole.USER,
        content="Hello world",
        token_estimate=2,
        created_at=now,
    )
    assert msg.id == msg_id
    assert msg.role == MessageRole.USER
    assert msg.content == "Hello world"
    assert msg.token_estimate == 2


def test_run_dto_creation():
    now = datetime.now(UTC)
    run_id = str(uuid.uuid4())
    run = RunDTO(
        id=run_id,
        owner_id="default",
        session_id=None,
        status=RunStatus.QUEUED,
        provider="grok",
        model="grok-2",
        budget_counters={"max_turns": 5},
        created_at=now,
    )
    assert run.id == run_id
    assert run.status == RunStatus.QUEUED
    assert run.provider == "grok"


def test_icarus_config_defaults():
    cfg = IcarusConfig()
    assert cfg.default_provider == "grok"
    assert cfg.model == "grok-2"
    assert cfg.temperature == 0.7
    assert cfg.max_turns == 25
    assert cfg.max_tokens_budget == 128000


def test_credential_source_enum():
    assert CredentialSource.CLI_ARG == "cli_arg"
    assert CredentialSource.ENV_VAR == "env_var"
    assert CredentialSource.KEYRING == "keyring"
    assert CredentialSource.NONE == "none"


def test_credential_result_model():
    res = CredentialResult(
        provider="grok",
        secret="xai-secret-12345",
        source=CredentialSource.ENV_VAR,
        masked="xai-...2345",
    )
    assert res.provider == "grok"
    assert res.secret == "xai-secret-12345"
    assert res.source == CredentialSource.ENV_VAR
    assert res.masked == "xai-...2345"


def test_token_usage_contract():
    usage = TokenUsage(prompt_tokens=15, completion_tokens=30)
    assert usage.prompt_tokens == 15
    assert usage.completion_tokens == 30
    assert usage.total_tokens == 45


def test_tenant_identity_contract_and_immutability():
    import pytest
    from icarus_contracts import TenantIdentity
    from pydantic import ValidationError

    identity = TenantIdentity(owner_id="tenant-123", token="secret-token-xyz")
    assert identity.owner_id == "tenant-123"
    assert identity.token == "secret-token-xyz"

    # Verify immutability
    with pytest.raises(ValidationError):
        identity.owner_id = "tenant-hacked"


def test_tenant_access_denied_error_contract():
    from icarus_contracts import TenantAccessDeniedError

    err = TenantAccessDeniedError("Cross-tenant access forbidden")
    assert isinstance(err, PermissionError)
    assert str(err) == "Cross-tenant access forbidden"


def test_session_and_message_api_response_contracts():
    from datetime import UTC, datetime

    from icarus_contracts import (
        MessageResponse,
        SessionListResponse,
        SessionResponse,
        SessionSummaryDTO,
    )

    now = datetime.now(UTC)
    sess_resp = SessionResponse(
        id="sess-1",
        owner_id="tenant-1",
        mode="chat",
        title="Session Title",
        created_at=now,
        updated_at=now,
        message_count=2,
        run_count=1,
        total_estimated_tokens=50,
    )
    assert sess_resp.id == "sess-1"
    assert sess_resp.message_count == 2
    assert sess_resp.total_estimated_tokens == 50

    list_resp = SessionListResponse(
        items=[
            SessionSummaryDTO(
                id="sess-1",
                owner_id="tenant-1",
                mode="chat",
                title="Session Title",
                created_at=now,
                updated_at=now,
                message_count=2,
                run_count=1,
                total_estimated_tokens=50,
            )
        ],
        total=1,
        limit=50,
        offset=0,
    )
    assert list_resp.total == 1
    assert len(list_resp.items) == 1
    assert list_resp.limit == 50

    msg_resp = MessageResponse(
        id="msg-1",
        session_id="sess-1",
        owner_id="tenant-1",
        role="user",
        content="Hello!",
        token_estimate=5,
        created_at=now,
    )
    assert msg_resp.id == "msg-1"
    assert msg_resp.role == "user"
    assert msg_resp.content == "Hello!"


def test_sse_and_run_contracts():
    from datetime import UTC, datetime

    from icarus_contracts import (
        RunCancelResponse,
        RunCreateRequest,
        RunResponse,
        RunStatus,
        SSEEventPayload,
        SSEEventType,
    )

    # 1. SSE event types
    assert SSEEventType.TURN_START == "turn_start"
    assert SSEEventType.TOKEN == "token"
    assert SSEEventType.TOOL_START == "tool_start"
    assert SSEEventType.TOOL_END == "tool_end"
    assert SSEEventType.COMPACTION == "compaction"
    assert SSEEventType.RUN_COMPLETED == "run_completed"
    assert SSEEventType.RUN_CANCELLED == "run_cancelled"
    assert SSEEventType.RUN_FAILED == "run_failed"

    # 2. SSEEventPayload formatting
    token_event = SSEEventPayload.token(delta="Hello", run_id="run-1")
    assert token_event.event == SSEEventType.TOKEN
    assert token_event.data["delta"] == "Hello"
    assert token_event.data["run_id"] == "run-1"
    msg_str = token_event.to_sse_message()
    assert msg_str.startswith("event: token\n")
    assert 'data: {"delta": "Hello", "run_id": "run-1"}\n\n' in msg_str

    # 3. Tool events
    tool_start_ev = SSEEventPayload.tool_start(
        tool_name="read_file",
        arguments={"path": "README.md"},
        tool_call_id="call-123",
        run_id="run-1",
    )
    assert tool_start_ev.event == SSEEventType.TOOL_START
    assert tool_start_ev.data["tool_name"] == "read_file"

    tool_end_ev = SSEEventPayload.tool_end(
        tool_name="read_file",
        output="file content",
        tool_call_id="call-123",
        run_id="run-1",
    )
    assert tool_end_ev.event == SSEEventType.TOOL_END
    assert tool_end_ev.data["output"] == "file content"

    # 4. Compaction event
    comp_ev = SSEEventPayload.compaction(
        tokens_saved=120,
        original_message_count=10,
        compacted_message_count=4,
        run_id="run-1",
    )
    assert comp_ev.event == SSEEventType.COMPACTION
    assert comp_ev.data["tokens_saved"] == 120

    # 5. Terminal events
    completed_ev = SSEEventPayload.run_completed(
        run_id="run-1",
        result="Done!",
        budget_counters={"total_tokens": 150},
    )
    assert completed_ev.event == SSEEventType.RUN_COMPLETED
    assert completed_ev.data["result"] == "Done!"

    cancelled_ev = SSEEventPayload.run_cancelled(run_id="run-1", message="Interrupted")
    assert cancelled_ev.event == SSEEventType.RUN_CANCELLED

    failed_ev = SSEEventPayload.run_failed(
        run_id="run-1", error="API timeout", error_category="TimeoutError"
    )
    assert failed_ev.event == SSEEventType.RUN_FAILED
    assert failed_ev.data["error_category"] == "TimeoutError"

    # 6. RunCreateRequest & RunResponse & RunCancelResponse
    req = RunCreateRequest(prompt="Summarize repo", model="mock-model", auto_approve=True)
    assert req.prompt == "Summarize repo"
    assert req.auto_approve is True

    now = datetime.now(UTC)
    resp = RunResponse(
        id="run-1",
        owner_id="tenant-1",
        session_id="sess-1",
        status=RunStatus.RUNNING,
        created_at=now,
    )
    assert resp.id == "run-1"
    assert resp.status == RunStatus.RUNNING

    cancel_resp = RunCancelResponse(
        run_id="run-1",
        status=RunStatus.CANCELLED,
        cancelled=True,
        message="Active run cancelled successfully.",
    )
    assert cancel_resp.run_id == "run-1"
    assert cancel_resp.cancelled is True
