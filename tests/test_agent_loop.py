"""Tests for autonomous ReAct execution loop in icarus_core.agent.loop."""

from pathlib import Path

import pytest
from icarus_contracts.provider import PromptMessage
from icarus_contracts.session import MessageRole
from icarus_contracts.tools import ToolCall, ToolResult
from icarus_core.agent.approvals import ApprovalEngine, ApprovalPolicy
from icarus_core.agent.loop import AgentLoop
from icarus_core.providers.mock import MockProvider
from icarus_core.tools.registry import create_default_registry


class TrackingObserver:
    """Observer recording all agent loop events for assertions."""

    def __init__(self) -> None:
        self.tokens: list[str] = []
        self.tools_started: list[ToolCall] = []
        self.tools_ended: list[ToolResult] = []
        self.turns_started: list[int] = []
        self.turns_ended: list[int] = []

    def on_token(self, delta: str) -> None:
        self.tokens.append(delta)

    def on_tool_start(self, tool_call: ToolCall) -> None:
        self.tools_started.append(tool_call)

    def on_tool_end(self, tool_result: ToolResult) -> None:
        self.tools_ended.append(tool_result)

    def on_turn_start(self, turn: int) -> None:
        self.turns_started.append(turn)

    def on_turn_end(self, turn: int) -> None:
        self.turns_ended.append(turn)


@pytest.mark.asyncio
async def test_agent_loop_direct_text_response_single_turn():
    """AgentLoop returns immediately when model provides text without tool calls."""
    provider = MockProvider(responses=["Hello from Icarus!"])
    registry = create_default_registry()
    observer = TrackingObserver()

    loop = AgentLoop(
        provider=provider,
        tool_registry=registry,
        inject_system=False,
    )

    result = await loop.run(prompt="Hello", observer=observer)

    assert result.content == "Hello from Icarus!"
    assert result.total_turns == 1
    assert len(result.tool_calls) == 0
    assert len(result.tool_results) == 0
    assert len(observer.tokens) > 0
    assert "".join(observer.tokens).strip() == "Hello from Icarus!"
    assert observer.turns_started == [1]
    assert observer.turns_ended == [1]


@pytest.mark.asyncio
async def test_agent_loop_multi_turn_tool_execution(tmp_path: Path):
    """AgentLoop executes requested tool, feeds back output, and receives final answer."""
    test_file = tmp_path / "version.txt"
    test_file.write_text("version = 2.4.0", encoding="utf-8")

    tc = ToolCall(id="call_read_1", name="read_file", arguments={"path": "version.txt"})
    provider = MockProvider(
        responses=["The version is 2.4.0."],
        tool_calls_sequence=[[tc], None],  # Turn 1: tool call, Turn 2: final answer
    )

    registry = create_default_registry()
    observer = TrackingObserver()

    loop = AgentLoop(
        provider=provider,
        tool_registry=registry,
        workspace_root=tmp_path,
        inject_system=False,
    )

    result = await loop.run(prompt="What is the version in version.txt?", observer=observer)

    assert result.content == "The version is 2.4.0."
    assert result.total_turns == 2
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].name == "read_file"
    assert len(result.tool_results) == 1
    assert "version = 2.4.0" in result.tool_results[0].output

    # Verify message history contains user -> assistant (tool call) -> tool -> assistant (answer)
    roles = [m.role for m in result.messages]
    assert roles == [
        MessageRole.USER,
        MessageRole.ASSISTANT,
        MessageRole.TOOL,
        MessageRole.ASSISTANT,
    ]

    # Verify observer notifications
    assert len(observer.tools_started) == 1
    assert observer.tools_started[0].name == "read_file"
    assert len(observer.tools_ended) == 1
    assert "version = 2.4.0" in observer.tools_ended[0].output
    assert observer.turns_started == [1, 2]
    assert observer.turns_ended == [1, 2]


@pytest.mark.asyncio
async def test_agent_loop_rejection_policy_denies_tool(tmp_path: Path):
    """When approval engine denies tool, rejection error is fed to model."""
    tc = ToolCall(
        id="call_write_1",
        name="write_file",
        arguments={"path": "output.txt", "content": "malicious content"},
    )
    provider = MockProvider(
        responses=["I understand, I will not write the file."],
        tool_calls_sequence=[[tc], None],
    )

    registry = create_default_registry()
    approval_engine = ApprovalEngine(policy=ApprovalPolicy.DENY)

    loop = AgentLoop(
        provider=provider,
        tool_registry=registry,
        approval_engine=approval_engine,
        workspace_root=tmp_path,
        inject_system=False,
    )

    result = await loop.run(prompt="Write to output.txt")

    assert result.total_turns == 2
    assert len(result.tool_results) == 1
    assert "denied by approval policy" in result.tool_results[0].error.lower()
    assert result.content == "I understand, I will not write the file."


@pytest.mark.asyncio
async def test_agent_loop_turn_limit_guardrail():
    """AgentLoop halts cleanly when max_turns budget is exceeded."""
    tc = ToolCall(id="call_infinite", name="search", arguments={"pattern": "loop"})
    provider = MockProvider(
        responses=["Searching..."],
        tool_calls_sequence=[[tc]] * 10,  # Always request tool
    )

    registry = create_default_registry()

    loop = AgentLoop(
        provider=provider,
        tool_registry=registry,
        max_turns=3,
        inject_system=False,
    )

    result = await loop.run(prompt="Start infinite loop")

    assert result.total_turns == 3
    assert len(result.tool_calls) == 3
    assert "turn budget (3) reached" in result.content.lower()


@pytest.mark.asyncio
async def test_agent_loop_multiple_tool_calls_in_single_turn(tmp_path: Path):
    """AgentLoop executes multiple tool calls dispatched in a single turn."""
    (tmp_path / "a.txt").write_text("file a", encoding="utf-8")
    (tmp_path / "b.txt").write_text("file b", encoding="utf-8")

    tc1 = ToolCall(id="call_a", name="read_file", arguments={"path": "a.txt"})
    tc2 = ToolCall(id="call_b", name="read_file", arguments={"path": "b.txt"})

    provider = MockProvider(
        responses=["Both files read."],
        tool_calls_sequence=[[tc1, tc2], None],
    )

    registry = create_default_registry()
    loop = AgentLoop(
        provider=provider,
        tool_registry=registry,
        workspace_root=tmp_path,
        inject_system=False,
    )

    result = await loop.run(prompt="Read both a.txt and b.txt")

    assert result.total_turns == 2
    assert len(result.tool_calls) == 2
    assert "file a" in result.tool_results[0].output
    assert "file b" in result.tool_results[1].output
    assert result.content == "Both files read."


@pytest.mark.asyncio
async def test_agent_loop_missing_tool_handled_gracefully():
    """When model requests unknown tool, clean error result is returned to model."""
    tc = ToolCall(id="call_unknown", name="nonexistent_tool", arguments={})
    provider = MockProvider(
        responses=["I see the tool does not exist."],
        tool_calls_sequence=[[tc], None],
    )

    registry = create_default_registry()
    loop = AgentLoop(
        provider=provider,
        tool_registry=registry,
        inject_system=False,
    )

    result = await loop.run(prompt="Run something unknown")

    assert result.total_turns == 2
    assert len(result.tool_results) == 1
    assert "not found in registry" in result.tool_results[0].error.lower()
    assert result.content == "I see the tool does not exist."


@pytest.mark.asyncio
async def test_agent_loop_preserves_prior_messages():
    """AgentLoop honors existing conversation history passed in messages."""
    prior = [
        PromptMessage(role=MessageRole.USER, content="My name is Alice."),
        PromptMessage(role=MessageRole.ASSISTANT, content="Nice to meet you Alice."),
    ]
    provider = MockProvider(responses=["Your name is Alice."])
    loop = AgentLoop(provider=provider, inject_system=False)

    result = await loop.run(prompt="What is my name?", messages=prior)

    assert result.total_turns == 1
    assert result.content == "Your name is Alice."
    # Conversation history contains prior messages + new user prompt + assistant answer
    assert len(result.messages) == 4
    assert result.messages[0].content == "My name is Alice."
    assert result.messages[2].content == "What is my name?"
    assert result.messages[3].content == "Your name is Alice."
