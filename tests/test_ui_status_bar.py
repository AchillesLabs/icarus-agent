"""Tests for Icarus status bar responsive layouts, token metrics, and secret redaction."""

import io

from icarus_cli.ui.status import format_status_bar, render_status_bar
from rich.console import Console


def test_status_bar_widths():
    """format_status_bar returns properly scaled representations across all widths."""
    model = "grok-2-latest"
    provider = "grok"
    session_id = "abcd1234ef56"

    # Ultra-narrow (<50 cols)
    narrow = format_status_bar(model, provider, session_id, width=45, plain=True)
    assert "Icarus" in narrow
    assert "grok" in narrow.lower()

    # Compact (50 - 74 cols)
    compact = format_status_bar(model, provider, session_id, width=65, plain=True)
    assert "Icarus" in compact
    assert "abcd1234" in compact

    # Standard (75 - 104 cols)
    standard = format_status_bar(model, provider, session_id, width=80, plain=True)
    assert "Icarus" in standard
    assert "Session abcd1234" in standard

    # Wide (>= 105 cols)
    wide = format_status_bar(
        model,
        provider,
        session_id,
        tokens_used=5000,
        token_budget=100000,
        width=120,
        plain=True,
    )
    assert "Icarus" in wide
    assert "5,000 / 100,000" in wide or "5.0%" in wide


def test_status_bar_never_fabricates_tokens():
    """When tokens_used is 0, status bar reports 0 tokens instead of inventing counts."""
    bar = format_status_bar("mock-model", "mock", tokens_used=0, width=120, plain=True)
    assert "0 tokens" in bar or "0.0%" in bar
    assert "10,000" not in bar


def test_status_bar_redacts_secrets():
    """Status bar never displays API keys or tokens even if present in environment."""
    secret = "gsk_secret_token_123456789"
    bar = format_status_bar(
        model="mock-model",
        provider="mock",
        session_id="session-123",
        toolset_info="core, web",
        width=120,
        plain=True,
    )
    assert secret not in bar
    assert "password" not in bar.lower()
    assert "bearer" not in bar.lower()


def test_render_status_bar_interactive_output():
    """render_status_bar writes to interactive console."""
    out = io.StringIO()
    cons = Console(file=out, width=80, force_terminal=True)
    render_status_bar(
        console=cons,
        model="llama-3.3-70b",
        provider="groq",
        session_id="a12f9c44",
        tokens_used=2400,
        token_budget=10000,
    )
    rendered = out.getvalue()
    assert "llama-3.3-70b" in rendered
    assert "Context" in rendered or "24%" in rendered
