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
