"""Tests for standardized Rich UI formatters (success, warning, error, panels)."""

import io

from icarus_cli.ui.formatters import (
    render_empty_state,
    render_error,
    render_key_value_panel,
    render_success,
    render_warning,
)
from rich.console import Console


def test_render_success():
    """render_success outputs green checkmark and message."""
    out = io.StringIO()
    cons = Console(file=out, width=80, force_terminal=True)
    render_success("Google account connected successfully.", console=cons)
    rendered = out.getvalue()
    assert "Google account connected successfully." in rendered
    assert "✓" in rendered or "✔" in rendered


def test_render_warning():
    """render_warning outputs yellow warning indicator."""
    out = io.StringIO()
    cons = Console(file=out, width=80, force_terminal=True)
    render_warning("API rate limit approaching 80%.", console=cons)
    rendered = out.getvalue()
    assert "API rate limit approaching 80%." in rendered
    assert "⚠" in rendered or "!" in rendered


def test_render_error_with_diagnosis_and_next_steps():
    """render_error displays structured diagnosis, reason, next steps, and reference ID."""
    out = io.StringIO()
    cons = Console(file=out, width=80, force_terminal=True)
    render_error(
        "Google authorization failed",
        reason="Invalid OAuth client configuration.",
        next_steps=[
            "Verify the configured OAuth client in ~/.icarus/config.toml.",
            "Check its redirect configuration in Google Cloud Console.",
            "Run: icarus integrations doctor google",
        ],
        reference_id="req_8f12c",
        console=cons,
    )
    rendered = out.getvalue()
    assert "Google authorization failed" in rendered
    assert "Invalid OAuth client configuration." in rendered
    assert "icarus integrations doctor google" in rendered
    assert "req_8f12c" in rendered


def test_render_key_value_panel():
    """render_key_value_panel renders formatted panel with aligned keys."""
    out = io.StringIO()
    cons = Console(file=out, width=80, force_terminal=True)
    render_key_value_panel(
        title="Session Overview",
        data={
            "Session ID": "sess_99182",
            "Model": "grok-2",
            "Status": "Active",
        },
        console=cons,
    )
    rendered = out.getvalue()
    assert "Session Overview" in rendered
    assert "sess_99182" in rendered
    assert "grok-2" in rendered


def test_render_empty_state():
    """render_empty_state presents clear guidance when no items exist."""
    out = io.StringIO()
    cons = Console(file=out, width=80, force_terminal=True)
    render_empty_state(
        "No skills installed",
        suggestion="Add a folder with SKILL.md to .agents/skills/ or run /skills pull <url>",
        console=cons,
    )
    rendered = out.getvalue()
    assert "No skills installed" in rendered
    assert "/skills pull" in rendered
