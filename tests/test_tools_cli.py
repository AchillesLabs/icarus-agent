"""Tests for CLI tools command suite and /tools inspection view."""

import io
from typer.testing import CliRunner
from rich.console import Console
from icarus_cli.main import app
from icarus_cli.tools_cmd import render_tools_table, render_tool_detail

runner = CliRunner()


def test_cli_tools_list_command():
    """icarus tools list outputs registered tools and their safety categories."""
    result = runner.invoke(app, ["tools", "list"])
    assert result.exit_code == 0
    assert "Available Tools" in result.output
    assert "read_file" in result.output
    assert "run_command" in result.output
    assert "write_file" in result.output
    assert "Requires Approval" in result.output
    assert "Safe (Auto)" in result.output


def test_cli_tools_show_valid_tool():
    """icarus tools show <name> displays parameter schema and descriptions."""
    result = runner.invoke(app, ["tools", "show", "write_file"])
    assert result.exit_code == 0
    assert "Tool Details: write_file" in result.output
    assert "Parameters Schema" in result.output
    assert "path" in result.output
    assert "content" in result.output


def test_cli_tools_show_nonexistent_tool():
    """icarus tools show <invalid> cleanly reports tool not found."""
    result = runner.invoke(app, ["tools", "show", "nonexistent_fake_tool"])
    assert result.exit_code == 0
    assert "not found" in result.output.lower()


def test_render_tools_table_and_detail_to_console():
    """render_tools_table and render_tool_detail output formatted tables to Rich console."""
    out = io.StringIO()
    cons = Console(file=out, width=100)
    render_tools_table(cons)
    rendered = out.getvalue()
    assert "read_file" in rendered

    out2 = io.StringIO()
    cons2 = Console(file=out2, width=100)
    render_tool_detail(cons2, "run_command")
    detail_rendered = out2.getvalue()
    assert "command" in detail_rendered
    assert "Parameters Schema" in detail_rendered
