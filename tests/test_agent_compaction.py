"""Integration tests for AgentLoop compaction integration and token budget guardrails."""

import pytest
from icarus_contracts import (
    CompactionResult,
    ContextBudgetConfig,
    MessageRole,
    PromptMessage,
    ToolCall,
)
from icarus_core.agent.compactor import HistoryCompactor
from icarus_core.agent.context import ContextBudgetManager
from icarus_core.agent.loop import AgentLoop, AgentLoopObserver
from icarus_core.providers.mock import MockProvider
from icarus_core.tokens import HeuristicTokenCounter


class CompactionTrackingObserver(AgentLoopObserver):
    """Observer capturing compaction and token budget events."""

    def __init__(self) -> None:
        self.tokens: list[str] = []
        self.compactions: list[CompactionResult] = []
        self.max_tokens_hit: list[int] = []
        self.turns_started: list[int] = []

    def on_token(self, delta: str) -> None:
        self.tokens.append(delta)

    def on_turn_start(self, turn: int) -> None:
        self.turns_started.append(turn)

    def on_turn_end(self, turn: int) -> None:
        pass

    def on_tool_start(self, tool_call: ToolCall) -> None:
        pass

    def on_tool_end(self, tool_result) -> None:
        pass

    def on_max_turns(self, max_turns: int) -> None:
        pass

    def on_compaction(self, event: CompactionResult) -> None:
        self.compactions.append(event)

    def on_max_tokens(self, max_tokens: int) -> None:
        self.max_tokens_hit.append(max_tokens)


@pytest.mark.asyncio
async def test_agent_loop_triggers_compaction_when_budget_exceeded():
    """Verify that when message history approaches input budget, compaction triggers."""
    # Context budget: window=800, output_reserve=100, safety_margin=100 -> input_budget = 600
    # compaction_threshold = 0.5 -> trigger = 300 tokens
    counter = HeuristicTokenCounter(chars_per_token=4.0)
    cfg = ContextBudgetConfig(
        context_window=800,
        output_reserve=100,
        safety_margin=100,
        compaction_threshold=0.5,
    )
    budget_mgr = ContextBudgetManager(config=cfg, token_counter=counter)
    compactor = HistoryCompactor(token_counter=counter, min_retained_turns=1)

    # Initial history with heavy content (>1000 tokens)
    huge_log = "ERROR 404 Not Found in server module at line 42\n" * 150
    prior_history = [
        PromptMessage(role=MessageRole.USER, content=f"Analyze this huge log file:\n{huge_log}"),
        PromptMessage(
            role=MessageRole.ASSISTANT, content="I analyzed the log files and found errors."
        ),
        PromptMessage(role=MessageRole.USER, content="Now please summarize the conclusions."),
    ]

    provider = MockProvider(responses=["The conclusion is that the server was misconfigured."])
    observer = CompactionTrackingObserver()

    loop = AgentLoop(
        provider=provider,
        budget_manager=budget_mgr,
        compactor=compactor,
        inject_system=False,
    )

    result = await loop.run(
        messages=prior_history,
        observer=observer,
    )

    # Assert compaction triggered
    assert len(observer.compactions) == 1
    compaction_event = observer.compactions[0]
    assert compaction_event.tokens_saved > 0
    assert result.compaction_count == 1

    # Assert conversation continuity and answer received
    assert result.content == "The conclusion is that the server was misconfigured."
    assert result.finish_reason == "stop"

    # Assert messages in result contain the summary message
    summary_messages = [
        m for m in result.messages if "## [Previous Conversation Summary]" in (m.content or "")
    ]
    assert len(summary_messages) == 1


@pytest.mark.asyncio
async def test_agent_loop_preserves_tool_pair_during_compaction():
    """Verify compaction within AgentLoop preserves assistant tool calls and tool results."""
    counter = HeuristicTokenCounter(chars_per_token=4.0)
    cfg = ContextBudgetConfig(
        context_window=900,
        output_reserve=100,
        safety_margin=100,
        compaction_threshold=0.5,
    )
    budget_mgr = ContextBudgetManager(config=cfg, token_counter=counter)
    compactor = HistoryCompactor(token_counter=counter, min_retained_turns=1)

    tc = ToolCall(id="call_inspect_1", name="read_file", arguments={"path": "large_file.txt"})
    history = [
        PromptMessage(
            role=MessageRole.USER,
            content="Read large file:\n" + ("Lorem ipsum dolor sit amet " * 40),
        ),
        PromptMessage(role=MessageRole.ASSISTANT, content="Reading...", tool_calls=[tc]),
        PromptMessage(
            role=MessageRole.TOOL,
            content="Large file content:\n" + ("data chunk " * 50),
            name="read_file",
            tool_call_id="call_inspect_1",
        ),
        PromptMessage(role=MessageRole.ASSISTANT, content="File read successfully."),
        PromptMessage(role=MessageRole.USER, content="What is the final summary?"),
    ]

    provider = MockProvider(responses=["Final summary complete."])
    observer = CompactionTrackingObserver()

    loop = AgentLoop(
        provider=provider,
        budget_manager=budget_mgr,
        compactor=compactor,
        inject_system=False,
    )

    result = await loop.run(messages=history, observer=observer)

    assert result.content == "Final summary complete."
    assert result.finish_reason == "stop"

    # Verify no tool messages were severed
    for i, m in enumerate(result.messages):
        if m.role == MessageRole.TOOL:
            assert i > 0
            assert result.messages[i - 1].role == MessageRole.ASSISTANT
            assert result.messages[i - 1].tool_calls is not None


@pytest.mark.asyncio
async def test_agent_loop_enforces_max_total_tokens_guardrail():
    """Verify AgentLoop halts cleanly when max_total_tokens ceiling is reached."""
    # MockProvider returns 20 tokens per completion
    provider = MockProvider(
        responses=["Step 1", "Step 2", "Step 3"],
        tool_calls_sequence=[
            [ToolCall(id="t1", name="search", arguments={"query": "test"})],
            [ToolCall(id="t2", name="search", arguments={"query": "test2"})],
            None,
        ],
    )
    observer = CompactionTrackingObserver()

    loop = AgentLoop(
        provider=provider,
        max_turns=10,
        max_total_tokens=25,  # Low ceiling, should halt after first turn
        inject_system=False,
    )

    result = await loop.run(prompt="Begin search task", observer=observer)

    assert result.finish_reason == "max_tokens"
    assert len(observer.max_tokens_hit) == 1
    assert observer.max_tokens_hit[0] == 25
    assert result.total_tokens >= 25


@pytest.mark.asyncio
async def test_agent_loop_accumulates_budget_counters():
    """Verify AgentLoopResult contains accumulated token and turn telemetry."""
    provider = MockProvider(responses=["Done."])

    loop = AgentLoop(
        provider=provider,
        inject_system=False,
    )

    result = await loop.run(prompt="Hello")

    assert result.total_turns == 1
    assert result.total_tokens > 0
    assert result.prompt_tokens > 0
    assert result.completion_tokens > 0
    assert "total_tokens" in result.budget_counters
    assert "prompt_tokens" in result.budget_counters
    assert "completion_tokens" in result.budget_counters
