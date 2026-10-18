"""Tests for hard turn limit enforcement, notifications, and config wiring."""

import pytest
from icarus_cli.observer import RichAgentObserver
from icarus_contracts.provider import StreamChunk
from icarus_contracts.tools import ToolCall, ToolDefinition, ToolResult
from icarus_core.agent.approvals import ApprovalEngine, ApprovalPolicy
from icarus_core.agent.loop import AgentLoop, AgentLoopObserver
from icarus_core.config import ConfigManager
from icarus_core.providers.mock import MockProvider
from icarus_core.tools.base import BaseTool
from icarus_core.tools.registry import ToolRegistry
from rich.console import Console


class DummyTool(BaseTool):
    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="dummy_tool",
            description="Dummy tool for testing turn limits.",
            parameters={"type": "object", "properties": {}},
        )

    def execute(self, arguments, workspace_root, call_id="test"):
        return ToolResult(call_id=call_id, name="dummy_tool", output="dummy ok")


class RecordingObserver(AgentLoopObserver):
    def __init__(self):
        self.turns_started: list[int] = []
        self.turns_ended: list[int] = []
        self.max_turns_notified: int | None = None

    def on_token(self, delta: str) -> None:
        pass

    def on_tool_start(self, tool_call: ToolCall) -> None:
        pass

    def on_tool_end(self, tool_result: ToolResult) -> None:
        pass

    def on_turn_start(self, turn: int) -> None:
        self.turns_started.append(turn)

    def on_turn_end(self, turn: int) -> None:
        self.turns_ended.append(turn)

    def on_max_turns(self, max_turns: int) -> None:
        self.max_turns_notified = max_turns


@pytest.mark.asyncio
async def test_agent_loop_terminates_at_hard_turn_limit():
    """Verify AgentLoop halts when max_turns is reached and notifies observer."""
    # Setup mock provider that always returns a tool call (runaway loop)
    provider = MockProvider()

    def mock_stream(*args, **kwargs):
        async def gen():
            yield StreamChunk(
                delta="",
                finish_reason="tool_calls",
                tool_calls=[
                    ToolCall(
                        id="call_dummy",
                        name="dummy_tool",
                        arguments={},
                    )
                ],
            )

        return gen()

    provider.stream = mock_stream

    registry = ToolRegistry()
    registry.register(DummyTool())
    approval_engine = ApprovalEngine(policy=ApprovalPolicy.AUTO_APPROVE)

    agent_loop = AgentLoop(
        provider=provider,
        tool_registry=registry,
        approval_engine=approval_engine,
        max_turns=3,
    )

    observer = RecordingObserver()
    result = await agent_loop.run(prompt="Loop forever please", observer=observer)

    assert result.total_turns == 3
    assert result.finish_reason == "max_turns"
    assert "Maximum turn budget (3) reached." in result.content
    assert observer.max_turns_notified == 3
    assert observer.turns_started == [1, 2, 3]

    # Verify that the last message is an assistant message informing about turn budget
    last_msg = result.messages[-1]
    assert last_msg.content == "Maximum turn budget (3) reached."


def test_rich_observer_renders_max_turns_panel():
    """Verify RichAgentObserver displays a clear notice when on_max_turns is triggered."""
    console = Console(record=True, width=100)
    observer = RichAgentObserver(console=console)

    observer.on_max_turns(25)
    output = console.export_text()

    assert "Turn Limit" in output or "Budget" in output
    assert "25" in output


def test_config_manager_default_and_custom_max_turns(tmp_path):
    """Verify ConfigManager respects default 25 max_turns and allows persistence."""
    cfg_file = tmp_path / "config.toml"
    cfg_mgr = ConfigManager(config_path=cfg_file)

    config = cfg_mgr.load_config()
    assert config.max_turns == 25

    # Update max_turns
    updated = cfg_mgr.set("max_turns", 15)
    assert updated.max_turns == 15

    # Reload from disk
    reloaded_mgr = ConfigManager(config_path=cfg_file)
    assert reloaded_mgr.load_config().max_turns == 15
