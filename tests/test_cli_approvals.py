"""Tests for CLI interactive approval prompt and Rich panel previews."""

import io
from pathlib import Path

from icarus_cli.approvals import create_cli_approval_engine, prompt_for_approval
from icarus_contracts.tools import ToolCall
from icarus_core.agent.approvals import ApprovalPolicy
from icarus_core.tools.filesystem import WriteFileTool
from rich.console import Console


def test_prompt_for_approval_displays_styled_panel_and_accepts_yes():
    """prompt_for_approval renders Rich panel with path and returns True for 'y'."""
    output = io.StringIO()
    console = Console(file=output, force_terminal=False, width=80)
    stdin = io.StringIO("y\n")

    tool = WriteFileTool()
    call = ToolCall(
        id="call_1",
        name="write_file",
        arguments={"path": "src/hello.py", "content": "print('hello')\n"},
    )

    approved = prompt_for_approval(
        tool_call=call,
        tool_definition=tool.definition,
        console=console,
        stdin=stdin,
    )

    assert approved is True
    rendered = output.getvalue()
    assert "Safety Approval Required" in rendered
    assert "src/hello.py" in rendered
    assert "print('hello')" in rendered


def test_prompt_for_approval_rejects_on_no_or_enter():
    """prompt_for_approval returns False when user enters 'n' or presses Enter."""
    output = io.StringIO()
    console = Console(file=output, force_terminal=False, width=80)
    stdin_no = io.StringIO("n\n")

    tool = WriteFileTool()
    call = ToolCall(
        id="call_2",
        name="write_file",
        arguments={"path": "delete_me.txt", "content": "data"},
    )

    assert not prompt_for_approval(call, tool.definition, console=console, stdin=stdin_no)

    stdin_enter = io.StringIO("\n")
    assert not prompt_for_approval(call, tool.definition, console=console, stdin=stdin_enter)


def test_create_cli_approval_engine_with_auto_approve():
    """create_cli_approval_engine sets AUTO_APPROVE when auto_approve=True."""
    engine = create_cli_approval_engine(auto_approve=True)
    assert engine.policy == ApprovalPolicy.AUTO_APPROVE

    tool = WriteFileTool()
    call = ToolCall(id="call_3", name="write_file", arguments={"path": "a.txt", "content": "x"})
    decision = engine.evaluate(call, tool.definition)
    assert decision.approved is True


def test_create_cli_approval_engine_interactive_execution(tmp_path: Path):
    """create_cli_approval_engine dispatches to prompt callback and executes write."""
    output = io.StringIO()
    console = Console(file=output, force_terminal=False)
    stdin = io.StringIO("yes\n")

    engine = create_cli_approval_engine(auto_approve=False, console=console, stdin=stdin)
    assert engine.policy == ApprovalPolicy.INTERACTIVE

    tool = WriteFileTool()
    call = ToolCall(
        id="call_exec",
        name="write_file",
        arguments={"path": "cli_written.txt", "content": "Approved via CLI prompt"},
    )

    result = engine.execute_with_approval(call, tool, workspace_root=tmp_path)
    assert result.exit_code == 0
    assert (tmp_path / "cli_written.txt").read_text(encoding="utf-8") == "Approved via CLI prompt"


def test_cli_approval_engine_interactive_rejection_leaves_workspace_clean(tmp_path: Path):
    """When user rejects in CLI prompt, write does not occur and clean refusal is returned."""
    output = io.StringIO()
    console = Console(file=output, force_terminal=False)
    stdin = io.StringIO("no\n")

    engine = create_cli_approval_engine(auto_approve=False, console=console, stdin=stdin)
    tool = WriteFileTool()
    call = ToolCall(
        id="call_rejected",
        name="write_file",
        arguments={"path": "forbidden.txt", "content": "Should not be written"},
    )

    result = engine.execute_with_approval(call, tool, workspace_root=tmp_path)
    assert result.exit_code == 1
    assert "rejected" in result.error.lower()
    assert not (tmp_path / "forbidden.txt").exists()


def test_cli_approval_engine_workspace_escape_blocked_even_if_approved(tmp_path: Path):
    """Even if an action is approved, workspace jailing still blocks traversal outside root."""
    output = io.StringIO()
    console = Console(file=output, force_terminal=False)
    stdin = io.StringIO("y\n")

    engine = create_cli_approval_engine(auto_approve=False, console=console, stdin=stdin)
    tool = WriteFileTool()
    call = ToolCall(
        id="call_escape",
        name="write_file",
        arguments={"path": "../escaped_write.txt", "content": "malicious payload"},
    )

    result = engine.execute_with_approval(call, tool, workspace_root=tmp_path)
    assert result.exit_code == 1
    assert "escapes workspace boundary" in result.error.lower()
    assert not (tmp_path.parent / "escaped_write.txt").exists()


def test_cli_prompt_eof_safely_defaults_to_no():
    """Empty EOF from stdin safely rejects the operation."""
    output = io.StringIO()
    console = Console(file=output, force_terminal=False)
    stdin = io.StringIO("")  # EOF immediately

    tool = WriteFileTool()
    call = ToolCall(
        id="call_eof",
        name="write_file",
        arguments={"path": "eof.txt", "content": "data"},
    )

    approved = prompt_for_approval(call, tool.definition, console=console, stdin=stdin)
    assert approved is False


def test_prompt_for_approval_renders_run_command_preview_and_accepts():
    """prompt_for_approval renders Rich panel with command, cwd, timeout and accepts 'y'."""
    from icarus_core.tools import RunCommandTool

    output = io.StringIO()
    console = Console(file=output, force_terminal=False, width=80)
    stdin = io.StringIO("y\n")

    tool = RunCommandTool()
    call = ToolCall(
        id="call_cli_cmd",
        name="run_command",
        arguments={"command": "pytest -v", "cwd": "tests", "timeout": 45.0},
    )

    approved = prompt_for_approval(
        tool_call=call,
        tool_definition=tool.definition,
        console=console,
        stdin=stdin,
    )

    assert approved is True
    rendered = output.getvalue()
    assert "Safety Approval Required" in rendered
    assert "Execute Shell Command" in rendered
    assert "pytest -v" in rendered
    assert "tests" in rendered
    assert "45" in rendered


def test_create_cli_approval_engine_interactive_run_command_rejection(tmp_path: Path):
    """create_cli_approval_engine rejects run_command when user inputs 'n'."""
    from icarus_core.tools import RunCommandTool

    output = io.StringIO()
    console = Console(file=output, force_terminal=False)
    stdin = io.StringIO("n\n")

    engine = create_cli_approval_engine(auto_approve=False, console=console, stdin=stdin)
    tool = RunCommandTool()
    canary = tmp_path / "cli_rejected.txt"
    cmd = f"python -c \"from pathlib import Path; Path(r'{canary}').write_text('bad')\""
    call = ToolCall(
        id="call_cli_reject",
        name="run_command",
        arguments={"command": cmd},
    )

    result = engine.execute_with_approval(call, tool, workspace_root=tmp_path)
    assert result.exit_code == 1
    assert "rejected" in result.error.lower()
    assert not canary.exists()


def test_payment_approval_displays_financial_warning_panel():
    """Payment tool prompts display prominent financial warning panel and arguments."""
    output = io.StringIO()
    console = Console(file=output, force_terminal=False, width=80)
    stdin = io.StringIO("y\n")

    call = ToolCall(
        id="call_pay_1",
        name="transfer_payment",
        arguments={"amount": 499.00, "currency": "USD", "recipient": "Delta Airlines"},
    )

    approved = prompt_for_approval(tool_call=call, console=console, stdin=stdin)
    assert approved is True
    rendered = output.getvalue()
    assert "Financial Payment Approval Required" in rendered
    assert "CRITICAL FINANCIAL / PAYMENT ACTION" in rendered
    assert "transfer_payment" in rendered
    assert "499" in rendered
    assert "Delta Airlines" in rendered


def test_booking_approval_displays_reservation_panel():
    """Booking tool prompts display green reservation confirmation panel."""
    output = io.StringIO()
    console = Console(file=output, force_terminal=False, width=80)
    stdin = io.StringIO("y\n")

    call = ToolCall(
        id="call_book_1",
        name="book_flight",
        arguments={"origin": "DEL", "destination": "PAT", "date": "2026-10-25"},
    )

    approved = prompt_for_approval(tool_call=call, console=console, stdin=stdin)
    assert approved is True
    rendered = output.getvalue()
    assert "Booking / Reservation Approval Required" in rendered
    assert "book_flight" in rendered
    assert "PAT" in rendered


def test_scheduling_approval_displays_calendar_panel():
    """Scheduling tool prompts display calendar panel and event details."""
    output = io.StringIO()
    console = Console(file=output, force_terminal=False, width=80)
    stdin = io.StringIO("y\n")

    call = ToolCall(
        id="call_sched_1",
        name="create_calendar_event",
        arguments={"title": "Sprint Review", "time": "2026-10-21 14:00"},
    )

    approved = prompt_for_approval(tool_call=call, console=console, stdin=stdin)
    assert approved is True
    rendered = output.getvalue()
    assert "Calendar / Schedule Approval Required" in rendered
    assert "Sprint Review" in rendered
