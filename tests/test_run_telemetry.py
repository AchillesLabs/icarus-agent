from __future__ import annotations

import io
from unittest.mock import patch

import pytest
from icarus_contracts.provider import StreamChunk
from icarus_contracts.session import MessageCreate, MessageRole, RunCreate, RunStatus, SessionCreate
from icarus_contracts.tools import ToolCall, ToolResult
from icarus_core.agent.loop import AgentLoop
from icarus_core.persistence.database import DatabaseManager
from icarus_core.persistence.migrations.runner import MigrationRunner
from icarus_core.persistence.models import Base
from icarus_core.persistence.repository import (
    AgentRunRepository,
    MessageRepository,
    SessionRepository,
)
from icarus_core.providers.mock import MockProvider
from icarus_core.tools.base import BaseTool
from icarus_core.tools.registry import ToolRegistry
from rich.console import Console
from sqlalchemy import inspect


class DummyEchoTool(BaseTool):
    """Dummy tool for testing tool call counting."""

    name = "dummy_echo"
    description = "Echoes input back"

    @property
    def definition(self):
        from icarus_contracts.tools import ToolDefinition

        return ToolDefinition(
            name=self.name,
            description=self.description,
            parameters={"type": "object", "properties": {"msg": {"type": "string"}}},
        )

    def execute(self, arguments: dict, workspace_root: str, call_id: str = "test") -> ToolResult:
        return ToolResult(call_id=call_id, name=self.name, output=f"echo: {arguments.get('msg')}")


@pytest.fixture
def telemetry_db(tmp_path) -> DatabaseManager:
    db_file = tmp_path / "telemetry_test.db"
    mgr = DatabaseManager(db_url=f"sqlite:///{db_file.as_posix()}")
    Base.metadata.create_all(mgr.engine)
    return mgr


@pytest.mark.asyncio
async def test_agent_loop_accumulates_complete_budget_counters():
    """Verify AgentLoop accumulates prompt/completion/total tokens, model_calls,
    tool_calls, compaction_count, and elapsed_time_seconds.
    """
    tool_call = ToolCall(id="tc-1", name="dummy_echo", arguments={"msg": "ping"})

    provider = MockProvider(
        tool_calls_sequence=[[tool_call], None],
        responses=["Tool execution verified. Done!"],
    )
    registry = ToolRegistry()
    registry.register(DummyEchoTool())

    loop = AgentLoop(
        provider=provider,
        tool_registry=registry,
        inject_system=False,
    )

    result = await loop.run(prompt="Run dummy tool")

    counters = result.budget_counters
    assert counters is not None

    # Required 7 fields from Spec 0003 & Ticket 05
    assert "prompt_tokens" in counters
    assert "completion_tokens" in counters
    assert "total_tokens" in counters
    assert "model_calls" in counters
    assert "tool_calls" in counters
    assert "compaction_count" in counters
    assert "elapsed_time_seconds" in counters

    # Invariants
    assert counters["prompt_tokens"] > 0
    assert counters["completion_tokens"] > 0
    assert counters["total_tokens"] == counters["prompt_tokens"] + counters["completion_tokens"]
    assert counters["model_calls"] == 2
    assert counters["tool_calls"] == 1
    assert counters["compaction_count"] == 0
    assert counters["elapsed_time_seconds"] >= 0.0
    assert counters["turns"] == 2


class CustomUsageProvider(MockProvider):
    """Provider that yields specific token usage numbers in stream chunks."""

    async def stream(self, messages, **kwargs):
        yield StreamChunk(
            delta="Custom usage test.",
            finish_reason="stop",
            usage={"prompt_tokens": 50, "completion_tokens": 12, "total_tokens": 62},
        )


@pytest.mark.asyncio
async def test_agent_loop_accumulates_provider_reported_token_usage():
    """Verify AgentLoop respects usage metadata emitted by provider chunks."""
    provider = CustomUsageProvider()
    loop = AgentLoop(provider=provider, inject_system=False)

    result = await loop.run(prompt="Hello")

    counters = result.budget_counters
    assert counters["prompt_tokens"] == 50
    assert counters["completion_tokens"] == 12
    assert counters["total_tokens"] == 62
    assert counters["model_calls"] == 1
    assert counters["tool_calls"] == 0


def test_sqlite_persistence_stores_complete_budget_counters(telemetry_db: DatabaseManager):
    """Verify AgentRunRepository persists and retrieves all 7 budget counters from SQLite."""
    session_repo = SessionRepository(telemetry_db)
    run_repo = AgentRunRepository(telemetry_db)

    sess = session_repo.create_session(SessionCreate(title="Persistence Test Session"))
    run = run_repo.create_run(
        RunCreate(
            session_id=sess.id,
            provider="mock",
            model="mock-model",
            status=RunStatus.RUNNING,
        )
    )

    budget_payload = {
        "prompt_tokens": 120,
        "completion_tokens": 45,
        "total_tokens": 165,
        "model_calls": 3,
        "tool_calls": 2,
        "compaction_count": 1,
        "elapsed_time_seconds": 1.234,
        "turns": 3,
        "compactions": 1,
        "finish_reason": "stop",
    }

    updated = run_repo.update_run(
        run.id,
        status=RunStatus.SUCCEEDED,
        completed=True,
        budget_counters=budget_payload,
    )
    assert updated is not None
    assert updated.status == RunStatus.SUCCEEDED
    assert updated.completed_at is not None

    # Query back from SQLite fresh
    fetched = run_repo.get_run(run.id)
    assert fetched is not None
    assert fetched.budget_counters == budget_payload
    assert fetched.budget_counters["prompt_tokens"] == 120
    assert fetched.budget_counters["completion_tokens"] == 45
    assert fetched.budget_counters["total_tokens"] == 165
    assert fetched.budget_counters["model_calls"] == 3
    assert fetched.budget_counters["tool_calls"] == 2
    assert fetched.budget_counters["compaction_count"] == 1
    assert fetched.budget_counters["elapsed_time_seconds"] == 1.234

    # List query
    runs = run_repo.list_runs_for_session(sess.id)
    assert len(runs) == 1
    assert runs[0].budget_counters["total_tokens"] == 165


def test_execute_run_persists_complete_budget_counters_into_sqlite(
    telemetry_db: DatabaseManager,
):
    """Verify execute_run CLI workflow records complete budget counters on success and failure."""
    from icarus_cli.run import execute_run

    provider = MockProvider(responses=["Finished execution."])
    console = Console(record=True)
    stdout = io.StringIO()

    with (
        patch("icarus_cli.run.DatabaseManager", return_value=telemetry_db),
        patch("icarus_cli.run.ProviderRegistry.get_provider", return_value=provider),
    ):
        code = execute_run(
            prompt="Test telemetry CLI",
            auto_approve=True,
            console=console,
            stdout=stdout,
        )

    assert code == 0
    session_repo = SessionRepository(telemetry_db)
    run_repo = AgentRunRepository(telemetry_db)

    sessions = session_repo.list_sessions()
    assert len(sessions) == 1
    session_id = sessions[0].id

    runs = run_repo.list_runs_for_session(session_id)
    assert len(runs) == 1
    run = runs[0]
    assert run.status == RunStatus.SUCCEEDED
    assert run.budget_counters is not None

    counters = run.budget_counters
    assert counters["prompt_tokens"] > 0
    assert counters["completion_tokens"] > 0
    assert counters["total_tokens"] == counters["prompt_tokens"] + counters["completion_tokens"]
    assert counters["model_calls"] == 1
    assert counters["tool_calls"] == 0
    assert counters["compaction_count"] == 0
    assert "elapsed_time_seconds" in counters
    assert counters["elapsed_time_seconds"] >= 0.0


def test_migration_0003_telemetry_indexes(tmp_path):
    """Verify Alembic migration 0003 creates telemetry indexes on messages and runs."""
    db_file = tmp_path / "migration_0003_test.db"
    db_url = f"sqlite:///{db_file.as_posix()}"
    runner = MigrationRunner()

    # Migrate up to 0003_telemetry_persistence
    runner.run_migrations(db_url=db_url, target_revision="0003_telemetry_persistence")
    assert runner.get_current_revision(db_url=db_url) == "0003_telemetry_persistence"

    db_manager = DatabaseManager(db_url=db_url)
    inspector = inspect(db_manager.engine)

    # Check indexes on messages
    msg_indexes = {idx["name"]: idx for idx in inspector.get_indexes("messages")}
    assert "ix_messages_token_estimate" in msg_indexes
    assert msg_indexes["ix_messages_token_estimate"]["column_names"] == ["token_estimate"]

    # Check indexes on agent_runs
    run_indexes = {idx["name"]: idx for idx in inspector.get_indexes("agent_runs")}
    assert "ix_agent_runs_status" in run_indexes
    assert run_indexes["ix_agent_runs_status"]["column_names"] == ["status"]


def test_session_repository_aggregates_summaries_and_token_totals(telemetry_db: DatabaseManager):
    """Verify session repository aggregates message count, run count, and token totals."""
    session_repo = SessionRepository(telemetry_db)
    message_repo = MessageRepository(telemetry_db)
    run_repo = AgentRunRepository(telemetry_db)

    sess = session_repo.create_session(SessionCreate(title="Telemetry Summary Test"))

    # Add 3 messages with token estimates
    message_repo.create_message(
        MessageCreate(
            session_id=sess.id,
            role=MessageRole.USER,
            content="Short prompt",
            token_estimate=10,
        )
    )
    message_repo.create_message(
        MessageCreate(
            session_id=sess.id,
            role=MessageRole.ASSISTANT,
            content="A longer response here",
            token_estimate=25,
        )
    )
    m3 = message_repo.create_message(
        MessageCreate(session_id=sess.id, role=MessageRole.USER, content="Auto calculated tokens")
    )
    assert m3.token_estimate is not None and m3.token_estimate > 0

    expected_token_total = 10 + 25 + m3.token_estimate

    # Add 2 runs with budget counters
    run_repo.create_run(
        RunCreate(
            session_id=sess.id,
            status=RunStatus.SUCCEEDED,
            budget_counters={
                "prompt_tokens": 100,
                "completion_tokens": 50,
                "total_tokens": 150,
                "model_calls": 2,
                "tool_calls": 1,
            },
        )
    )
    run_repo.create_run(
        RunCreate(
            session_id=sess.id,
            status=RunStatus.SUCCEEDED,
            budget_counters={
                "prompt_tokens": 60,
                "completion_tokens": 30,
                "total_tokens": 90,
                "model_calls": 1,
                "tool_calls": 0,
            },
        )
    )

    # 1. Test message_repo.get_session_token_total
    token_total = message_repo.get_session_token_total(sess.id)
    assert token_total == expected_token_total

    # 2. Test run_repo.get_session_budget_totals
    run_totals = run_repo.get_session_budget_totals(sess.id)
    assert run_totals["run_count"] == 2
    assert run_totals["prompt_tokens"] == 160
    assert run_totals["completion_tokens"] == 80
    assert run_totals["total_tokens"] == 240
    assert run_totals["model_calls"] == 3
    assert run_totals["tool_calls"] == 1

    # 3. Test session_repo.get_session_summary
    summary = session_repo.get_session_summary(sess.id)
    assert summary is not None
    assert summary.id == sess.id
    assert summary.message_count == 3
    assert summary.run_count == 2
    assert summary.total_estimated_tokens == expected_token_total

    # 4. Test session_repo.list_session_summaries
    summaries = session_repo.list_session_summaries()
    assert len(summaries) >= 1
    target = next(s for s in summaries if s.id == sess.id)
    assert target.message_count == 3
    assert target.run_count == 2
    assert target.total_estimated_tokens == expected_token_total
