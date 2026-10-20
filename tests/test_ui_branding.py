"""Tests for Icarus UI branding, ASCII artwork, and responsive banner layouts."""

import io

from icarus_cli.ui.branding import (
    ICARUS_PLAIN_LOGO,
    get_ascii_logo,
    get_banner,
    get_compact_logo,
    get_sprite,
    render_banner,
    render_logo,
)
from rich.console import Console


def test_ascii_logo_rendering_and_plain_fallback():
    """ASCII logo returns original artwork and plain fallback behaves properly."""
    ascii_art = get_ascii_logo()
    assert "I C A R U S" in ascii_art
    assert "YOUR PERSONAL AI RUNTIME" in ascii_art

    compact_styled = get_compact_logo(plain=False)
    assert "I C A R U S" in compact_styled

    compact_plain = get_compact_logo(plain=True)
    assert compact_plain == ICARUS_PLAIN_LOGO

    banner_styled = get_banner(plain=False)
    assert "I C A R U S" in banner_styled

    sprite = get_sprite(plain=True)
    assert "☼" in sprite or "\\" in sprite


def test_render_logo_to_console():
    """render_logo outputs to Rich console in full, compact, and plain modes."""
    # Full mode
    out_full = io.StringIO()
    cons_full = Console(file=out_full, width=100, force_terminal=True)
    render_logo(console=cons_full, compact=False, plain=False)
    assert "I C A R U S" in out_full.getvalue()

    # Compact mode
    out_compact = io.StringIO()
    cons_compact = Console(file=out_compact, width=100, force_terminal=True)
    render_logo(console=cons_compact, compact=True, plain=False)
    assert "I C A R U S" in out_compact.getvalue()

    # Plain mode
    out_plain = io.StringIO()
    cons_plain = Console(file=out_plain, width=100, force_terminal=False)
    render_logo(console=cons_plain, compact=False, plain=True)
    assert "I C A R U S" in out_plain.getvalue()


def test_render_banner_terminal_widths():
    """render_banner renders reliably at widths 40, 60, 80, and 120 columns."""
    for width in (40, 60, 80, 120):
        out = io.StringIO()
        cons = Console(file=out, width=width, force_terminal=True)
        render_banner(
            console=cons,
            model="grok-2-latest",
            provider="grok",
            session_id="test-session-12345678",
            tokens_used=1024,
            token_budget=128000,
            no_banner=False,
        )
        rendered = out.getvalue()
        assert len(rendered) > 0
        assert "grok" in rendered or "I C A R U S" in rendered


def test_render_banner_no_banner_option():
    """When no_banner=True, render_banner outputs nothing."""
    out = io.StringIO()
    cons = Console(file=out, width=80, force_terminal=True)
    render_banner(
        console=cons,
        model="grok-2",
        provider="grok",
        no_banner=True,
    )
    assert out.getvalue() == ""


def test_render_banner_plain_mode():
    """Plain mode outputs clean unstyled text without crashing."""
    out = io.StringIO()
    cons = Console(file=out, width=80, force_terminal=False)
    render_banner(
        console=cons,
        model="mock-model",
        provider="mock",
        session_id="sess-abc",
        plain=True,
    )
    rendered = out.getvalue()
    assert "I C A R U S" in rendered
    assert "mock-model" in rendered
    assert "sess-abc" in rendered
