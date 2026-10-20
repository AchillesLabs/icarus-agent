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


def test_cli_tools_catalog_command():
    """icarus tools catalog displays essential connectors including Gmail, Calendar, and Composio."""
    result = runner.invoke(app, ["tools", "catalog"])
    assert result.exit_code == 0
    assert "Essential Tool Connectors Catalog" in result.output
    assert "gmail" in result.output.lower()
    assert "calendar" in result.output.lower()
    assert "composio" in result.output.lower()
    assert "browser" in result.output.lower()


def test_get_connector_with_aliases():
    """get_connector resolves both exact IDs and friendly aliases."""
    from icarus_core.tools.catalog import get_connector

    assert get_connector("gmail") is not None
    assert get_connector("gmail").id == "gmail"
    assert get_connector("email") is not None
    assert get_connector("email").id == "gmail"
    assert get_connector("mail").id == "gmail"
    assert get_connector("google").id == "gmail"

    assert get_connector("calendar").id == "calendar"
    assert get_connector("cal").id == "calendar"
    assert get_connector("gcal").id == "calendar"

    assert get_connector("composio").id == "composio"
    assert get_connector("apps").id == "composio"

    assert get_connector("browser").id == "browser"
    assert get_connector("puppeteer").id == "browser"

    assert get_connector("nonexistent_connector") is None


def test_cli_connect_gmail_interactive(monkeypatch):
    """icarus connect gmail prompts for credentials and saves them safely."""
    from unittest.mock import patch
    from icarus_core.tools.auth import ToolAuthManager

    with patch("webbrowser.open") as mock_open:
        # Simulate entering email and app password
        result = runner.invoke(app, ["connect", "gmail"], input="testuser@gmail.com\nabcdefghijklmnop\n")
        assert result.exit_code == 0
        assert "Connecting Gmail" in result.output
        assert "Successfully connected Gmail" in result.output
        assert ToolAuthManager.get_token("gmail") == "testuser@gmail.com:abcdefghijklmnop"
        mock_open.assert_called_once()


def test_cli_connect_browser_no_auth():
    """icarus connect browser connects Puppeteer without requiring API keys."""
    from unittest.mock import patch
    from icarus_core.mcp.config import McpConfigManager

    with patch("webbrowser.open"):
        result = runner.invoke(app, ["connect", "browser"])
        assert result.exit_code == 0
        assert "Successfully connected" in result.output
        assert "Zero keys required" in result.output
        cfg = McpConfigManager().get_server("browser")
        assert cfg is not None
        assert cfg.command == "npx"


def test_cli_connect_unknown_connector():
    """icarus connect <invalid> gives clean error and points to catalog."""
    result = runner.invoke(app, ["connect", "totally_unknown_service"])
    assert result.exit_code == 0
    assert "Unknown connector ID 'totally_unknown_service'" in result.output
    assert "icarus tools catalog" in result.output

