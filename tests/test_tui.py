"""Unit and integration tests for Full-Screen TUI Workspace and header rendering."""

import io
from pathlib import Path
from unittest.mock import patch

import pytest
from icarus_cli.main import app
from icarus_cli.observer import RichAgentObserver
from icarus_cli.tui import (
    ESC_CLEAR_SCREEN,
    ESC_ENTER_ALT_SCREEN,
    ESC_HOME_CURSOR,
    ESC_LEAVE_ALT_SCREEN,
    ESC_SHOW_CURSOR,
    AlternateScreenBuffer,
    InteractivePrompt,
    render_workspace_header,
)
from icarus_contracts.tools import ToolCall, ToolResult
from rich.console import Console
from typer.testing import CliRunner

runner = CliRunner()


def test_alternate_screen_buffer_enter_and_exit_escape_sequences():
    """AlternateScreenBuffer writes correct ANSI escape codes to enter and leave alt screen."""
    stream = io.StringIO()
    alt = AlternateScreenBuffer(stream=stream, force=True)

    assert not alt.is_active
    alt.enter()
    assert alt.is_active

    output = stream.getvalue()
    assert ESC_ENTER_ALT_SCREEN in output
    assert ESC_CLEAR_SCREEN in output
    assert ESC_HOME_CURSOR in output
    assert ESC_SHOW_CURSOR in output

    alt.exit()
    assert not alt.is_active

    output_after = stream.getvalue()
    assert ESC_LEAVE_ALT_SCREEN in output_after


def test_alternate_screen_buffer_context_manager_guarantees_cleanup():
    """AlternateScreenBuffer context manager guarantees screen buffer exit even on error."""
    stream = io.StringIO()

    with (
        pytest.raises(RuntimeError, match="Simulated crash"),
        AlternateScreenBuffer(stream=stream, force=True),
    ):
        assert ESC_ENTER_ALT_SCREEN in stream.getvalue()
        raise RuntimeError("Simulated crash")

    # Exit code must be present despite the exception
    assert ESC_LEAVE_ALT_SCREEN in stream.getvalue()


def test_alternate_screen_buffer_inactive_when_not_tty():
    """By default, without force, stream.isatty() == False skips escape sequences."""
    stream = io.StringIO()  # not a tty
    alt = AlternateScreenBuffer(stream=stream, force=False)

    assert not alt.should_activate
    with alt:
        assert not alt.is_active
        assert stream.getvalue() == ""


def test_render_workspace_header_content_and_styling():
    """render_workspace_header formats application title, model, provider, tokens, and session."""
    string_io = io.StringIO()
    console = Console(file=string_io, width=120, force_terminal=True, color_system="standard")

    render_workspace_header(
        console=console,
        model="grok-2-latest",
        provider="grok",
        session_id="test-session-uuid-1234",
        tokens_used=15420,
        token_budget=128000,
        mode="Autonomous Personal Agent",
    )

    rendered = string_io.getvalue()
    assert "ICARUS AGENT CHAT" in rendered
    assert "grok-2-latest" in rendered
    assert "grok" in rendered
    assert "test-session-uuid-1234" in rendered
    assert "15,420" in rendered
    assert "128,000" in rendered
    assert "Autonomous Personal Agent" in rendered


def test_render_workspace_header_remote_badge():
    """render_workspace_header displays REMOTE status badge when remote_url is provided."""
    string_io = io.StringIO()
    console = Console(file=string_io, width=120, force_terminal=True, color_system="standard")

    render_workspace_header(
        console=console,
        model="claude-3-7-sonnet",
        provider="openrouter",
        session_id="remote-sess-5678",
        tokens_used=500,
        token_budget=200000,
        remote_url="http://agent.local:8000",
    )

    rendered = string_io.getvalue()
    assert "REMOTE" in rendered
    assert "http://agent.local:8000" in rendered
    assert "claude-3-7-sonnet" in rendered


def test_tool_progress_panels_specialized_formatting():
    """RichAgentObserver categorizes tool calls and renders specialized icons and borders."""
    string_io = io.StringIO()
    console = Console(file=string_io, width=100, force_terminal=True, color_system="standard")
    observer = RichAgentObserver(console=console)

    # 1. Web search
    call_search = ToolCall(id="c1", name="web_search", arguments='{"query": "flight NYC to LON"}')
    observer.on_tool_start(call_search)
    res_search = ToolResult(
        call_id="c1",
        name="web_search",
        output="Result 1: British Airways $450\nResult 2: Delta $480",
    )
    observer.on_tool_end(res_search)

    # 2. Browser action
    call_browser = ToolCall(
        id="c2", name="fetch_webpage", arguments='{"url": "https://expedia.com"}'
    )
    observer.on_tool_start(call_browser)
    res_browser = ToolResult(
        call_id="c2",
        name="fetch_webpage",
        output="Expedia Flights Booking Page Content...",
    )
    observer.on_tool_end(res_browser)

    # 3. MCP tool
    call_mcp = ToolCall(
        id="c3", name="mcp_puppeteer_click", arguments='{"selector": "#submit-btn"}'
    )
    observer.on_tool_start(call_mcp)
    res_mcp = ToolResult(
        call_id="c3",
        name="mcp_puppeteer_click",
        output="Clicked element #submit-btn successfully",
    )
    observer.on_tool_end(res_mcp)

    # 4. Background reminder
    call_remind = ToolCall(
        id="c4",
        name="schedule_reminder",
        arguments='{"time": "in 2 hours", "task": "Check prices"}',
    )
    observer.on_tool_start(call_remind)
    res_remind = ToolResult(
        call_id="c4",
        name="schedule_reminder",
        output="Job #42 scheduled for execution at 18:00 UTC",
    )
    observer.on_tool_end(res_remind)

    output = string_io.getvalue()
    assert "Web Intelligence Search" in output
    assert "web_search" in output
    assert "Browser Automation" in output
    assert "fetch_webpage" in output
    assert "Model Context Protocol (MCP)" in output
    assert "mcp_puppeteer_click" in output
    assert "Background Task Scheduler" in output
    assert "schedule_reminder" in output
    assert "Preview: Result 1: British Airways $450" in output


def test_interactive_prompt_fallback_and_history(tmp_path: Path):
    """InteractivePrompt reads input from stdin stream in non-interactive environment."""
    hist_file = tmp_path / "test_history"
    stdin = io.StringIO("Hello Jarvis\n/exit\n")
    prompt = InteractivePrompt(stdin=stdin, history_file=hist_file)

    line1 = prompt.read_input()
    assert line1 == "Hello Jarvis"
    line2 = prompt.read_input()
    assert line2 == "/exit"

    with pytest.raises(EOFError):
        prompt.read_input()


def test_default_icarus_launches_chat(tmp_path: Path):
    """Running `icarus` with no arguments launches into interactive chat workspace."""
    db_file = tmp_path / "icarus.db"
    with (
        patch("icarus_core.paths.get_icarus_home", return_value=tmp_path),
        patch("icarus_core.paths.get_icarus_db_path", return_value=db_file),
    ):
        result = runner.invoke(app, [], input="/exit\n")
        assert result.exit_code == 0
        assert "ICARUS AGENT CHAT" in result.stdout or "Session" in result.stdout
        assert "Goodbye" in result.stdout or "Exiting" in result.stdout
