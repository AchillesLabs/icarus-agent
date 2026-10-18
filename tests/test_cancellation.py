"""Tests for clean SIGINT / Ctrl+C cancellation, state preservation, and process cleanup."""

import asyncio

import pytest
from icarus_contracts.provider import PromptMessage, StreamChunk
from icarus_contracts.session import MessageCreate, MessageRole, SessionCreate
from icarus_contracts.tools import ToolCall, ToolDefinition, ToolResult
from icarus_core.agent.approvals import ApprovalEngine, ApprovalPolicy
from icarus_core.agent.loop import AgentLoop
from icarus_core.persistence.database import DatabaseManager
from icarus_core.persistence.models import Base
from icarus_core.persistence.repository import MessageRepository, SessionRepository
from icarus_core.providers.mock import MockProvider
from icarus_core.tools.base import BaseTool
from icarus_core.tools.registry import ToolRegistry


@pytest.fixture
def in_memory_db() -> DatabaseManager:
    manager = DatabaseManager(db_url="sqlite:///:memory:")
    Base.metadata.create_all(manager.engine)
    return manager


class InterruptibleTool(BaseTool):
    def __init__(self, raise_interrupt: bool = True):
        self.raise_interrupt = raise_interrupt

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="interrupt_tool",
            description="Tool that simulates user pressing Ctrl+C",
            parameters={"type": "object", "properties": {}},
        )

    def execute(self, arguments, workspace_root, call_id="test"):
        if self.raise_interrupt:
            raise KeyboardInterrupt("Simulated Ctrl+C during tool execution")
        return ToolResult(call_id=call_id, name="interrupt_tool", output="ok")


@pytest.mark.asyncio
async def test_cancellation_during_model_streaming(in_memory_db: DatabaseManager):
    """Verify SIGINT during streaming stops loop, marks cancelled, and saves partial state."""
    session_repo = SessionRepository(in_memory_db)
    message_repo = MessageRepository(in_memory_db)
    sess = session_repo.create_session(SessionCreate(title="Stream Interruption"))

    # Record user message
    message_repo.create_message(
        MessageCreate(
            session_id=sess.id,
            role=MessageRole.USER,
            content="Tell me a very long story",
        )
    )

    persisted_messages: list[PromptMessage] = []

    def on_message(msg: PromptMessage):
        persisted_messages.append(msg)
        message_repo.create_message(
            MessageCreate(
                session_id=sess.id,
                role=msg.role,
                content=msg.content or "",
                tool_calls=msg.tool_calls,
                tool_call_id=msg.tool_call_id,
                name=msg.name,
            )
        )

    provider = MockProvider()

    def mock_stream(*args, **kwargs):
        async def gen():
            yield StreamChunk(delta="Once upon a time ")
            yield StreamChunk(delta="in a distant galaxy ")
            raise KeyboardInterrupt("Simulated Ctrl+C in model stream")

        return gen()

    provider.stream = mock_stream

    agent_loop = AgentLoop(
        provider=provider,
        message_callback=on_message,
        max_turns=5,
    )

    result = await agent_loop.run(prompt="Tell me a very long story")

    assert result.finish_reason == "cancelled"
    assert "Once upon a time in a distant galaxy" in result.content
    assert "interrupted" in result.content.lower()

    # Verify messages in SQLite
    db_messages = message_repo.list_messages(sess.id)
    assert len(db_messages) >= 2  # user message + interrupted assistant message
    last_db_msg = db_messages[-1]
    assert last_db_msg.role == MessageRole.ASSISTANT
    assert "Once upon a time" in (last_db_msg.content or "")


@pytest.mark.asyncio
async def test_cancellation_during_tool_execution(in_memory_db: DatabaseManager):
    """Verify SIGINT during tool execution generates matching ToolResult and prevents
    corrupted state."""
    session_repo = SessionRepository(in_memory_db)
    message_repo = MessageRepository(in_memory_db)
    sess = session_repo.create_session(SessionCreate(title="Tool Interruption"))

    # Setup provider that yields a tool call
    provider = MockProvider()

    def mock_stream(*args, **kwargs):
        async def gen():
            yield StreamChunk(
                delta="I will run the command.",
                finish_reason="tool_calls",
                tool_calls=[
                    ToolCall(
                        id="call_slow_tool",
                        name="interrupt_tool",
                        arguments={},
                    )
                ],
            )

        return gen()

    provider.stream = mock_stream

    registry = ToolRegistry()
    registry.register(InterruptibleTool(raise_interrupt=True))
    approval_engine = ApprovalEngine(policy=ApprovalPolicy.AUTO_APPROVE)

    def on_message(msg: PromptMessage):
        message_repo.create_message(
            MessageCreate(
                session_id=sess.id,
                role=msg.role,
                content=msg.content or "",
                tool_calls=msg.tool_calls,
                tool_call_id=msg.tool_call_id,
                name=msg.name,
            )
        )

    agent_loop = AgentLoop(
        provider=provider,
        tool_registry=registry,
        approval_engine=approval_engine,
        message_callback=on_message,
        max_turns=5,
    )

    result = await agent_loop.run(prompt="Run slow tool")

    assert result.finish_reason == "cancelled"
    assert len(result.tool_results) == 1
    tool_res = result.tool_results[0]
    assert tool_res.call_id == "call_slow_tool"
    assert tool_res.exit_code == 130
    assert "cancelled by user" in (tool_res.error or "").lower()

    # Verify all messages persisted in database
    db_messages = message_repo.list_messages(sess.id)
    roles = [m.role for m in db_messages]

    # Must contain assistant (with tool_calls) and tool response (with matching tool_call_id)
    assert MessageRole.ASSISTANT in roles
    assert MessageRole.TOOL in roles

    tool_db_msg = next(m for m in db_messages if m.role == MessageRole.TOOL)
    assert tool_db_msg.tool_call_id == "call_slow_tool"
    assert tool_db_msg.name == "interrupt_tool"
    assert "cancelled by user" in (tool_db_msg.content or "").lower()


@pytest.mark.asyncio
async def test_cancellation_with_multiple_tool_calls(in_memory_db: DatabaseManager):
    """Verify that multiple tool calls in a turn all get matching results when interrupted."""
    session_repo = SessionRepository(in_memory_db)
    message_repo = MessageRepository(in_memory_db)
    sess = session_repo.create_session(SessionCreate(title="Multi-Tool Interruption"))

    provider = MockProvider()

    def mock_stream(*args, **kwargs):
        async def gen():
            yield StreamChunk(
                delta="",
                finish_reason="tool_calls",
                tool_calls=[
                    ToolCall(id="call_1", name="interrupt_tool", arguments={}),
                    ToolCall(id="call_2", name="interrupt_tool", arguments={}),
                ],
            )

        return gen()

    provider.stream = mock_stream

    registry = ToolRegistry()
    registry.register(InterruptibleTool(raise_interrupt=True))
    approval_engine = ApprovalEngine(policy=ApprovalPolicy.AUTO_APPROVE)

    def on_message(msg: PromptMessage):
        message_repo.create_message(
            MessageCreate(
                session_id=sess.id,
                role=msg.role,
                content=msg.content or "",
                tool_calls=msg.tool_calls,
                tool_call_id=msg.tool_call_id,
                name=msg.name,
            )
        )

    agent_loop = AgentLoop(
        provider=provider,
        tool_registry=registry,
        approval_engine=approval_engine,
        message_callback=on_message,
        max_turns=5,
    )

    result = await agent_loop.run(prompt="Run both tools")

    assert result.finish_reason == "cancelled"
    # Both tool calls should have matching results to prevent corrupted state
    assert len(result.tool_results) == 2
    assert result.tool_results[0].call_id == "call_1"
    assert result.tool_results[1].call_id == "call_2"

    db_messages = message_repo.list_messages(sess.id)
    tool_msgs = [m for m in db_messages if m.role == MessageRole.TOOL]
    assert len(tool_msgs) == 2
    assert {m.tool_call_id for m in tool_msgs} == {"call_1", "call_2"}


@pytest.mark.asyncio
async def test_run_command_tool_cancellation(tmp_path):
    """Verify RunCommandTool terminates child process cleanly when cancelled."""
    import sys

    from icarus_core.tools.command import RunCommandTool

    tool = RunCommandTool()
    cmd = f'"{sys.executable}" -c "import time; time.sleep(60)"'

    task = asyncio.create_task(
        tool.execute_async(
            arguments={"command": cmd, "timeout": 60.0},
            workspace_root=tmp_path,
            call_id="call_cancel_test",
        )
    )

    await asyncio.sleep(0.3)
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task
