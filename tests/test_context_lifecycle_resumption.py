"""End-to-end integration tests for Context Lifecycle, Compaction Persistence,
Session Resumption Integrity, and Cumulative Budget Aggregation (Ticket 07).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from icarus_cli.chat import ChatSessionManager, _is_chat_prompt_message
from icarus_contracts import (
    ContextBudgetConfig,
    MessageCreate,
    MessageRole,
    PromptMessage,
    RunCreate,
    RunStatus,
    SessionCreate,
    ToolCall,
    ToolDefinition,
    ToolResult,
)
from icarus_core.agent.compactor import HistoryCompactor
from icarus_core.agent.context import ContextBudgetManager
from icarus_core.agent.loop import AgentLoop
from icarus_core.agent.prompts import inject_system_prompt
from icarus_core.persistence.database import DatabaseManager
from icarus_core.persistence.models import Base
from icarus_core.persistence.repository import (
    AgentRunRepository,
    MessageRepository,
    SessionRepository,
)
from icarus_core.providers.mock import MockProvider
from icarus_core.tokens import HeuristicTokenCounter
from icarus_core.tools.base import BaseTool
from icarus_core.tools.registry import ToolRegistry


class DummySearchTool(BaseTool):
    """Test tool that tracks invocation count to verify tools are not re-executed."""

    def __init__(self) -> None:
        self.call_count = 0

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="search_knowledge",
            description="Search the knowledge base.",
            parameters={
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        )

    def execute(
        self,
        arguments: dict[str, Any],
        workspace_root: Path | str,
        call_id: str = "direct_call",
    ) -> ToolResult:
        self.call_count += 1
        return ToolResult(
            call_id=call_id,
            name=self.name,
            output=f"Knowledge results for '{arguments.get('query', '')}': System operational.",
        )


@pytest.fixture
def lifecycle_db(tmp_path: Path) -> DatabaseManager:
    db_file = tmp_path / "lifecycle.db"
    db_mgr = DatabaseManager(db_url=f"sqlite:///{db_file.as_posix()}")
    Base.metadata.create_all(db_mgr.engine)
    return db_mgr


@pytest.mark.asyncio
async def test_compaction_persistence_and_resumed_session_continuation(
    lifecycle_db: DatabaseManager,
):
    """Verify that a session undergoing compaction persists its summary, can be resumed,
    preserves safety guidelines, and does not re-execute compacted tools.
    """
    session_repo = SessionRepository(lifecycle_db)
    message_repo = MessageRepository(lifecycle_db)
    run_repo = AgentRunRepository(lifecycle_db)

    # 1. Create active session
    session = session_repo.create_session(
        SessionCreate(title="E2E Context Lifecycle Session", mode="chat")
    )

    # 2. Setup budget manager with small context window to trigger compaction
    counter = HeuristicTokenCounter(chars_per_token=4.0)
    cfg = ContextBudgetConfig(
        context_window=600,
        output_reserve=100,
        safety_margin=50,
        compaction_threshold=0.5,  # triggers at total_tokens >= 225
    )
    budget_mgr = ContextBudgetManager(config=cfg, token_counter=counter)
    compactor = HistoryCompactor(token_counter=counter, min_retained_turns=1)

    # 3. Populate session with initial multi-turn history containing heavy text and tool calls
    message_repo.create_message(
        MessageCreate(
            session_id=session.id,
            role=MessageRole.USER,
            content="Please inspect the cluster status and verify all node health logs:\n"
            + ("NODE_LOG_ENTRY: health=OK, cpu=4%, mem=12% | " * 35),
        )
    )

    tc1 = ToolCall(id="call_search_1", name="search_knowledge", arguments={"query": "node_health"})
    message_repo.create_message(
        MessageCreate(
            session_id=session.id,
            role=MessageRole.ASSISTANT,
            content="Querying the cluster knowledge base.",
            tool_calls=[tc1],
        )
    )

    message_repo.create_message(
        MessageCreate(
            session_id=session.id,
            role=MessageRole.TOOL,
            content="Knowledge results for 'node_health': System operational.",
            tool_call_id="call_search_1",
            name="search_knowledge",
        )
    )

    message_repo.create_message(
        MessageCreate(
            session_id=session.id,
            role=MessageRole.ASSISTANT,
            content="All nodes in the cluster are verified operational and healthy.",
        )
    )

    # 4. First run on this session: User asks a follow-up question
    message_repo.create_message(
        MessageCreate(
            session_id=session.id,
            role=MessageRole.USER,
            content="Now please check if any backup jobs are scheduled.",
        )
    )

    persisted_messages: list[PromptMessage] = []

    def on_message_persisted(msg: PromptMessage) -> None:
        persisted_messages.append(msg)
        message_repo.create_message(
            MessageCreate(
                session_id=session.id,
                role=msg.role,
                content=msg.content or "",
                tool_calls=msg.tool_calls,
                tool_call_id=msg.tool_call_id,
                name=msg.name,
            )
        )

    search_tool = DummySearchTool()
    tool_reg = ToolRegistry()
    tool_reg.register(search_tool)

    provider1 = MockProvider(
        responses=[
            "I see from our prior conversation that nodes are healthy. No backup jobs pending."
        ]
    )

    loop1 = AgentLoop(
        provider=provider1,
        tool_registry=tool_reg,
        budget_manager=budget_mgr,
        compactor=compactor,
        inject_system=True,
        message_callback=on_message_persisted,
    )

    # Load all session messages into prompt history for Run 1
    session_msgs = message_repo.list_messages(session.id)
    history1 = [m.to_prompt_message() for m in session_msgs if _is_chat_prompt_message(m)]

    result1 = await loop1.run(messages=history1)

    # Verify compaction occurred during Run 1
    assert result1.compaction_count >= 1
    assert result1.finish_reason == "stop"

    # Verify that the compaction summary message was persisted into SQLite
    persisted_summary_in_db = [
        m
        for m in message_repo.list_messages(session.id)
        if (m.role.value if hasattr(m.role, "value") else str(m.role)) == MessageRole.SYSTEM.value
        and "[Previous Conversation Summary]" in (m.content or "")
    ]
    assert len(persisted_summary_in_db) >= 1
    summary_content = persisted_summary_in_db[0].content
    assert "Original Task Goal" in summary_content
    assert "cluster" in summary_content.lower() or "node" in summary_content.lower()

    # 5. Record Run 1 in AgentRunRepository
    run1 = run_repo.create_run(
        RunCreate(
            session_id=session.id,
            status=RunStatus.SUCCEEDED,
            budget_counters=result1.budget_counters,
        )
    )
    assert run1.status == "succeeded"

    # -------------------------------------------------------------
    # 6. RESUME SESSION (Simulate new process / chat restart)
    # -------------------------------------------------------------
    session_mgr = ChatSessionManager(db_manager=lifecycle_db)
    resumed_session, was_resumed = session_mgr.resolve_session(session_id=session.id)
    assert was_resumed is True
    assert resumed_session.id == session.id

    # Verify loaded prompt history re-hydrates the compaction summary
    resumed_prompt_history = session_mgr.get_prompt_history(session.id)

    # Verify compaction summary is present in the restored prompt history
    summary_messages_in_resumed = [
        m
        for m in resumed_prompt_history
        if (m.role.value if hasattr(m.role, "value") else str(m.role)) == MessageRole.SYSTEM.value
        and "[Previous Conversation Summary]" in (m.content or "")
    ]
    assert len(summary_messages_in_resumed) == 1

    # Verify system prompt injection preserves both the system instructions AND the summary
    injected_messages = inject_system_prompt(resumed_prompt_history)
    assert len(injected_messages) >= 2
    # First message: dynamic system instructions (safety & persona)
    assert injected_messages[0].role == MessageRole.SYSTEM
    assert "Icarus" in (injected_messages[0].content or "")
    # Second message: preserved compaction summary
    assert injected_messages[1].role == MessageRole.SYSTEM
    assert "[Previous Conversation Summary]" in (injected_messages[1].content or "")

    # 7. Execute Run 2 on the resumed session: User asks another question
    message_repo.create_message(
        MessageCreate(
            session_id=session.id,
            role=MessageRole.USER,
            content="Can you search for the backup schedule once more?",
        )
    )

    # Initial call count of search tool was 0 during Run 1 (since Run 1 used mock answers directly)
    assert search_tool.call_count == 0

    tc2 = ToolCall(
        id="call_search_2", name="search_knowledge", arguments={"query": "backup_schedule"}
    )
    provider2 = MockProvider(
        responses=["The backup schedule is configured for 02:00 UTC daily."],
        tool_calls_sequence=[[tc2], None],
    )

    loop2 = AgentLoop(
        provider=provider2,
        tool_registry=tool_reg,
        budget_manager=budget_mgr,
        compactor=compactor,
        inject_system=True,
        message_callback=on_message_persisted,
    )

    resumed_history_for_run = session_mgr.get_prompt_history(session.id)

    result2 = await loop2.run(messages=resumed_history_for_run)
    assert result2.finish_reason == "stop"
    assert "02:00 UTC" in result2.content

    # Verify tool execution: search_knowledge called once in Run 2 (no duplicate calls)
    assert search_tool.call_count == 1

    # Record Run 2 in AgentRunRepository
    run2 = run_repo.create_run(
        RunCreate(
            session_id=session.id,
            status=RunStatus.SUCCEEDED,
            budget_counters=result2.budget_counters,
        )
    )
    assert run2.status == "succeeded"

    # 8. Verify cumulative budget counters across both runs in SQLite
    totals = run_repo.get_session_budget_totals(session.id)
    assert totals["run_count"] == 2
    assert totals["prompt_tokens"] > 0
    assert totals["completion_tokens"] > 0
    assert totals["total_tokens"] == totals["prompt_tokens"] + totals["completion_tokens"]
    assert totals["model_calls"] >= 3  # Run 1 (1 call) + Run 2 (2 calls)
    assert totals["tool_calls"] == 1  # 1 tool call executed in Run 2
    assert totals["compaction_count"] >= 1


def test_cumulative_budget_counter_aggregation_across_runs(lifecycle_db: DatabaseManager):
    """Verify that multiple agent runs on the same session aggregate tokens,
    tool calls, model calls, and compactions accurately in SQLite.
    """
    session_repo = SessionRepository(lifecycle_db)
    run_repo = AgentRunRepository(lifecycle_db)

    sess = session_repo.create_session(SessionCreate(title="Telemetry Accumulation", mode="run"))

    # Run 1: 150 prompt tokens, 50 completion, 1 call, 1 tool, 0 compactions
    run_repo.create_run(
        RunCreate(
            session_id=sess.id,
            status=RunStatus.SUCCEEDED,
            budget_counters={
                "prompt_tokens": 150,
                "completion_tokens": 50,
                "total_tokens": 200,
                "model_calls": 1,
                "tool_calls": 1,
                "compaction_count": 0,
                "elapsed_time_seconds": 1.25,
            },
        )
    )

    # Run 2: 300 prompt tokens, 100 completion, 2 calls, 3 tools, 1 compaction
    run_repo.create_run(
        RunCreate(
            session_id=sess.id,
            status=RunStatus.SUCCEEDED,
            budget_counters={
                "prompt_tokens": 300,
                "completion_tokens": 100,
                "total_tokens": 400,
                "model_calls": 2,
                "tool_calls": 3,
                "compaction_count": 1,
                "elapsed_time_seconds": 2.75,
            },
        )
    )

    # Run 3: 50 prompt tokens, 20 completion, 1 call, 0 tools, 0 compactions
    run_repo.create_run(
        RunCreate(
            session_id=sess.id,
            status=RunStatus.SUCCEEDED,
            budget_counters={
                "prompt_tokens": 50,
                "completion_tokens": 20,
                "total_tokens": 70,
                "model_calls": 1,
                "tool_calls": 0,
                "compaction_count": 0,
                "elapsed_time_seconds": 0.50,
            },
        )
    )

    # Verify aggregated session totals
    totals = run_repo.get_session_budget_totals(sess.id)
    assert totals["run_count"] == 3
    assert totals["prompt_tokens"] == 500
    assert totals["completion_tokens"] == 170
    assert totals["total_tokens"] == 670
    assert totals["model_calls"] == 4
    assert totals["tool_calls"] == 4
    assert totals["compaction_count"] == 1
    assert totals["elapsed_time_seconds"] == 4.5

    # Verify session summary query
    summary = session_repo.get_session_summary(sess.id)
    assert summary is not None
    assert summary.id == sess.id
    assert summary.run_count == 3


def test_tool_invariant_preservation_under_compaction_and_resumption():
    """Verify that compaction never separates assistant tool_calls from their tool results,
    and preserves atomic function-calling invariants across resumption.
    """
    counter = HeuristicTokenCounter(chars_per_token=4.0)
    compactor = HistoryCompactor(token_counter=counter, min_retained_turns=1)

    tc1 = ToolCall(id="c1", name="read_file", arguments={"path": "a.txt"})
    tc2 = ToolCall(id="c2", name="write_file", arguments={"path": "b.txt", "content": "data"})

    messages = [
        PromptMessage(role=MessageRole.USER, content="Step 1: please read a.txt"),
        PromptMessage(role=MessageRole.ASSISTANT, content="", tool_calls=[tc1]),
        PromptMessage(
            role=MessageRole.TOOL,
            content="File content of a.txt",
            tool_call_id="c1",
            name="read_file",
        ),
        PromptMessage(role=MessageRole.ASSISTANT, content="I read a.txt."),
        PromptMessage(role=MessageRole.USER, content="Step 2: please write b.txt"),
        PromptMessage(role=MessageRole.ASSISTANT, content="", tool_calls=[tc2]),
        PromptMessage(
            role=MessageRole.TOOL,
            content="Wrote b.txt successfully",
            tool_call_id="c2",
            name="write_file",
        ),
        PromptMessage(role=MessageRole.ASSISTANT, content="I wrote b.txt."),
        PromptMessage(role=MessageRole.USER, content="Step 3: final question"),
    ]

    # Compact retaining 1 turn
    res = compactor.compact(messages, keep_recent_count=2)
    assert res.tokens_saved >= 0

    # Retained messages must never begin with an orphaned TOOL message
    first_retained = res.retained_messages[0]
    assert first_retained.role != MessageRole.TOOL

    # If any assistant tool call is retained, its corresponding tool result must be present
    retained_call_ids = {c.id for m in res.retained_messages if m.tool_calls for c in m.tool_calls}
    retained_result_ids = {
        m.tool_call_id
        for m in res.retained_messages
        if m.role == MessageRole.TOOL and m.tool_call_id
    }
    assert retained_call_ids == retained_result_ids
