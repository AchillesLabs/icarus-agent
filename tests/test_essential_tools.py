"""Comprehensive tests for all Essential Personal Agent tools and external auth links."""

import io
from unittest.mock import patch

from icarus_core.tools.auth import ToolAuthManager
from icarus_core.tools.calendar import CalendarEventsTool
from icarus_core.tools.github import GithubIssuesTool
from icarus_core.tools.gmail import GmailSearchTool
from icarus_core.tools.http import HttpRequestTool
from icarus_core.tools.registry import create_default_registry
from icarus_core.tools.stripe import StripePaymentLinkTool
from icarus_core.tools.weather import GetWeatherTool
from rich.console import Console


def test_all_essential_tools_present_in_default_registry():
    """All personal agent essential tools (Muse-style) are registered by default."""
    registry = create_default_registry(load_mcp=False)
    names = [t.name for t in registry.list_tools()]

    expected = [
        "read_file",
        "write_file",
        "list_dir",
        "search",
        "run_command",
        "web_search",
        "fetch_webpage",
        "get_current_location",
        "schedule_reminder",
        "list_reminders",
        "http_request",
        "get_weather",
        "browser_navigate",
        "gmail_search",
        "gmail_send",
        "calendar_events",
        "calendar_create_event",
        "github_issues",
        "github_create_issue",
        "slack_send_message",
        "stripe_payment_link",
    ]

    for tool_name in expected:
        assert tool_name in names, f"Expected essential tool '{tool_name}' not in registry!"


def test_tool_auth_manager_storage_and_env():
    """ToolAuthManager saves and resolves tokens correctly."""
    ToolAuthManager.save_token("test_service", "secret_token_123")
    assert ToolAuthManager.get_token("test_service") == "secret_token_123"


def test_tool_auth_prompt_renders_link_and_collects_token():
    """prompt_authorization displays external URL and returns entered token."""
    out = io.StringIO()
    cons = Console(file=out, width=100)
    stdin = io.StringIO("test_google_password_999\n")

    token = ToolAuthManager.prompt_authorization("gmail", console=cons, stdin=stdin)
    assert token == "test_google_password_999"
    assert "https://myaccount.google.com/apppasswords" in out.getvalue()
    assert ToolAuthManager.get_token("gmail") == "test_google_password_999"


def test_gmail_unauthorized_gracefully_guides_user():
    """GmailSearchTool prompts or reports authorization link when token is empty."""
    tool = GmailSearchTool()
    with (
        patch.object(ToolAuthManager, "get_token", return_value=None),
        patch.object(ToolAuthManager, "prompt_authorization", return_value=None),
    ):
        res = tool.execute({"query": "is:unread"}, workspace_root=".")
        assert res.exit_code == 1
        assert "myaccount.google.com/apppasswords" in res.error


def test_calendar_unauthorized_gracefully_guides_user():
    """CalendarEventsTool reports authorization link when unauthenticated."""
    tool = CalendarEventsTool()
    with (
        patch.object(ToolAuthManager, "get_token", return_value=None),
        patch.object(ToolAuthManager, "prompt_authorization", return_value=None),
    ):
        res = tool.execute({"time_min": "today"}, workspace_root=".")
        assert res.exit_code == 1
        assert "myaccount.google.com/apppasswords" in res.error


def test_github_unauthorized_gracefully_guides_user():
    """GithubIssuesTool reports github token link when unauthenticated."""
    tool = GithubIssuesTool()
    with (
        patch.object(ToolAuthManager, "get_token", return_value=None),
        patch.object(ToolAuthManager, "prompt_authorization", return_value=None),
    ):
        res = tool.execute({"repo": "owner/repo"}, workspace_root=".")
        assert res.exit_code == 1
        assert "github.com/settings/tokens" in res.error


def test_stripe_unauthorized_gracefully_guides_user():
    """StripePaymentLinkTool reports stripe dashboard link when unauthenticated."""
    tool = StripePaymentLinkTool()
    with (
        patch.object(ToolAuthManager, "get_token", return_value=None),
        patch.object(ToolAuthManager, "prompt_authorization", return_value=None),
    ):
        res = tool.execute({"amount": 10.0, "item_name": "Pro"}, workspace_root=".")
        assert res.exit_code == 1
        assert "dashboard.stripe.com/apikeys" in res.error


def test_weather_tool_validation():
    """GetWeatherTool requires location parameter."""
    tool = GetWeatherTool()
    res = tool.execute({}, workspace_root=".")
    assert res.exit_code == 1
    assert "location" in res.error.lower()


def test_http_request_tool_validation():
    """HttpRequestTool validates URL scheme."""
    tool = HttpRequestTool()
    res = tool.execute({"url": "invalid_url"}, workspace_root=".")
    assert res.exit_code == 1
    assert "http://" in res.error
