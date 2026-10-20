"""Tests for standard box-format approval prompt defaulting to denial."""

import io

from icarus_cli.ui.approvals import format_action_preview, render_approval_prompt
from icarus_contracts.tools import ToolCall
from rich.console import Console


def test_approval_box_format_run_command():
    """format_action_preview renders command, directory, and safety details."""
    call = ToolCall(
        id="call_cmd_1",
        name="run_command",
        arguments={"command": "pytest tests/", "cwd": ".", "timeout": 30.0},
    )
    preview = format_action_preview(call)
    assert "pytest tests/" in preview
    assert "run_command" in preview
    assert "local command" in preview


def test_approval_box_format_file_write():
    """format_action_preview formats target path and content preview for file modifications."""
    call = ToolCall(
        id="call_write_1",
        name="write_file",
        arguments={"path": "src/app.py", "content": "print('hello world')\n"},
    )
    preview = format_action_preview(call)
    assert "src/app.py" in preview
    assert "print('hello world')" in preview
    assert "modifies or overwrites" in preview


def test_approval_defaults_strictly_to_denial():
    """Prompt defaults strictly to denial on empty input, 'n', random text, or EOF."""
    call = ToolCall(
        id="call_1",
        name="run_command",
        arguments={"command": "rm -rf tmp/"},
    )

    # Empty input (user pressed Enter)
    out = io.StringIO()
    cons = Console(file=out, width=80)
    assert not render_approval_prompt(call, console=cons, stdin=io.StringIO("\n"))

    # Explicit 'n'
    out = io.StringIO()
    cons = Console(file=out, width=80)
    assert not render_approval_prompt(call, console=cons, stdin=io.StringIO("n\n"))

    # Random text
    out = io.StringIO()
    cons = Console(file=out, width=80)
    assert not render_approval_prompt(call, console=cons, stdin=io.StringIO("maybe\n"))

    # EOF (stream closed or Ctrl+D)
    out = io.StringIO()
    cons = Console(file=out, width=80)
    assert not render_approval_prompt(call, console=cons, stdin=io.StringIO(""))


def test_approval_accepts_yes():
    """Prompt accepts 'y' and 'yes' (case-insensitive)."""
    call = ToolCall(
        id="call_1",
        name="run_command",
        arguments={"command": "git status"},
    )

    for affirmative in ("y\n", "Y\n", "yes\n", "YES\n"):
        out = io.StringIO()
        cons = Console(file=out, width=80)
        assert render_approval_prompt(call, console=cons, stdin=io.StringIO(affirmative))
