"""Tests for approval policy engine and human-in-the-loop decisions."""

from pathlib import Path

from icarus_contracts.tools import (
    ToolCall,
    ToolDefinition,
)
from icarus_core.agent.approvals import (
    ApprovalEngine,
    ApprovalPolicy,
)
from icarus_core.tools.filesystem import ReadFileTool, WriteFileTool


def test_approval_policy_enum_values():
    """ApprovalPolicy supports INTERACTIVE, AUTO_APPROVE, and DENY."""
    assert ApprovalPolicy.INTERACTIVE.value == "interactive"
    assert ApprovalPolicy.AUTO_APPROVE.value == "auto_approve"
    assert ApprovalPolicy.DENY.value == "deny"


def test_safe_read_tools_never_require_approval():
    """Tools with SAFE_READ bypass approval check regardless of policy."""
    engine = ApprovalEngine(policy=ApprovalPolicy.DENY)
    read_def = ReadFileTool().definition
    call = ToolCall(id="call_read", name="read_file", arguments={"path": "foo.txt"})

    decision = engine.evaluate(call, read_def)
    assert decision.approved is True
    assert not engine.requires_approval(read_def)


def test_auto_approve_policy_executes_write_without_callback(tmp_path: Path):
    """AUTO_APPROVE policy permits write_file without interactive prompt."""
    engine = ApprovalEngine(policy=ApprovalPolicy.AUTO_APPROVE)
    tool = WriteFileTool()
    call = ToolCall(
        id="call_auto_write",
        name="write_file",
        arguments={"path": "auto_approved.txt", "content": "Autonomous content"},
    )

    decision = engine.evaluate(call, tool.definition)
    assert decision.approved is True

    result = engine.execute_with_approval(call, tool, workspace_root=tmp_path)
    assert result.exit_code == 0
    assert result.error is None
    assert (tmp_path / "auto_approved.txt").read_text(encoding="utf-8") == "Autonomous content"


def test_deny_policy_rejects_destructive_operation(tmp_path: Path):
    """DENY policy immediately rejects write_file and leaves workspace unmodified."""
    engine = ApprovalEngine(policy=ApprovalPolicy.DENY)
    tool = WriteFileTool()
    call = ToolCall(
        id="call_deny_write",
        name="write_file",
        arguments={"path": "denied.txt", "content": "Should not exist"},
    )

    decision = engine.evaluate(call, tool.definition)
    assert decision.approved is False
    assert "DENY" in (decision.reason or "")

    result = engine.execute_with_approval(call, tool, workspace_root=tmp_path)
    assert result.exit_code == 1
    assert "denied" in result.error.lower()
    assert not (tmp_path / "denied.txt").exists()


def test_interactive_policy_user_accepts(tmp_path: Path):
    """INTERACTIVE policy executes write when callback returns True."""
    prompted_calls = []

    def mock_prompt(call: ToolCall, definition: ToolDefinition) -> bool:
        prompted_calls.append((call, definition))
        return True

    engine = ApprovalEngine(policy=ApprovalPolicy.INTERACTIVE, prompt_callback=mock_prompt)
    tool = WriteFileTool()
    call = ToolCall(
        id="call_user_yes",
        name="write_file",
        arguments={"path": "accepted.txt", "content": "User said yes"},
    )

    decision = engine.evaluate(call, tool.definition)
    assert decision.approved is True
    assert len(prompted_calls) == 1

    result = engine.execute_with_approval(call, tool, workspace_root=tmp_path)
    assert result.exit_code == 0
    assert (tmp_path / "accepted.txt").read_text(encoding="utf-8") == "User said yes"


def test_interactive_policy_user_rejects(tmp_path: Path):
    """INTERACTIVE policy cleanly rejects without crashing when user says No."""
    prompted_calls = []

    def mock_prompt(call: ToolCall, definition: ToolDefinition) -> bool:
        prompted_calls.append((call, definition))
        return False

    engine = ApprovalEngine(policy=ApprovalPolicy.INTERACTIVE, prompt_callback=mock_prompt)
    tool = WriteFileTool()
    call = ToolCall(
        id="call_user_no",
        name="write_file",
        arguments={"path": "rejected.txt", "content": "User said no"},
    )

    decision = engine.evaluate(call, tool.definition)
    assert decision.approved is False
    assert "rejected" in (decision.reason or "").lower()

    result = engine.execute_with_approval(call, tool, workspace_root=tmp_path)
    assert result.exit_code == 1
    assert "rejected" in result.error.lower()
    assert not (tmp_path / "rejected.txt").exists()

    # ToolResult can be converted into a message for the model without crashing
    prompt_msg = result.to_prompt_message()
    assert "rejected" in prompt_msg.content.lower()


def test_interactive_policy_missing_callback_rejects_safely(tmp_path: Path):
    """INTERACTIVE policy safely denies execution if no prompt callback is configured."""
    engine = ApprovalEngine(policy=ApprovalPolicy.INTERACTIVE, prompt_callback=None)
    tool = WriteFileTool()
    call = ToolCall(
        id="call_no_cb",
        name="write_file",
        arguments={"path": "test.txt", "content": "data"},
    )

    decision = engine.evaluate(call, tool.definition)
    assert decision.approved is False
    assert "no approval prompt callback" in (decision.reason or "")

    result = engine.execute_with_approval(call, tool, workspace_root=tmp_path)
    assert result.exit_code == 1
    assert "no approval prompt callback" in result.error.lower()
    assert not (tmp_path / "test.txt").exists()
