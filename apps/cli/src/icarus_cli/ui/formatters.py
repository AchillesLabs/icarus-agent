"""Standardized Rich presentation formatters for success, warning, error, and table outputs."""

from __future__ import annotations

import logging
from typing import Any

from icarus_core.theme import UITheme, get_theme
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

logger = logging.getLogger("icarus.cli.ui")


def render_success(
    message: str,
    details: list[str] | None = None,
    console: Console | None = None,
) -> None:
    """Render a clean success confirmation with optional bullet details."""
    cons = console or Console()
    cons.print(f"[bold green]✓[/bold green] [bold white]{message}[/bold white]")
    if details:
        for item in details:
            cons.print(f"  [dim]•[/dim] {item}")


def render_warning(
    message: str,
    details: str | list[str] | None = None,
    console: Console | None = None,
) -> None:
    """Render a noticeable warning panel or message without halting execution."""
    cons = console or Console()
    cons.print(f"[bold yellow]⚠[/bold yellow] [yellow]{message}[/yellow]")
    if details:
        if isinstance(details, str):
            cons.print(f"  [dim]{details}[/dim]")
        else:
            for item in details:
                cons.print(f"  [dim]•[/dim] {item}")


def render_error(
    message: str,
    reason: str | None = None,
    next_steps: list[str] | None = None,
    reference: str | None = None,
    reference_id: str | None = None,
    console: Console | None = None,
) -> None:
    """Render an actionable error panel with diagnostic context and remediation steps."""
    cons = console or Console()
    ref = reference or reference_id

    lines = [f"[bold red]✗ {message}[/bold red]"]

    if reason:
        lines.append(f"\n[bold white]Reason:[/bold white] [red]{reason}[/red]")

    if next_steps:
        lines.append("\n[bold white]Next steps:[/bold white]")
        for i, step in enumerate(next_steps, 1):
            lines.append(f"  [bold cyan]{i}.[/bold cyan] {step}")

    if ref:
        lines.append(f"\n[dim]Reference: {ref}[/dim]")

    panel = Panel(
        "\n".join(lines),
        title="[bold red]Error[/bold red]",
        border_style="red",
        padding=(0, 1),
    )
    cons.print(panel)


def render_key_value_panel(
    title: str,
    items: dict[str, Any] | None = None,
    data: dict[str, Any] | None = None,
    theme: UITheme | None = None,
    console: Console | None = None,
) -> None:
    """Render a structured key-value inspection card."""
    cons = console or Console()
    th = theme or get_theme()
    kv_items = items if items is not None else (data or {})

    table = Table.grid(padding=(0, 2))
    table.add_column(style=f"bold {th.primary}", min_width=16)
    table.add_column(style="white")

    for k, v in kv_items.items():
        v_str = str(v) if v is not None else "[dim]None[/dim]"
        table.add_row(k, v_str)

    panel = Panel(
        table,
        title=f"[bold {th.secondary}]{title}[/bold {th.secondary}]",
        border_style=th.border,
        padding=(0, 1),
    )
    cons.print(panel)


def render_section_header(
    title: str,
    subtitle: str | None = None,
    theme: UITheme | None = None,
    console: Console | None = None,
) -> None:
    """Render a styled section divider header."""
    cons = console or Console()
    th = theme or get_theme()

    header_text = f"[bold {th.secondary}]{title}[/bold {th.secondary}]"
    if subtitle:
        header_text += f" [dim]({subtitle})[/dim]"

    cons.print()
    cons.rule(header_text, style=th.border)
    cons.print()


def render_empty_state(
    title: str,
    message: str | None = None,
    hint: str | None = None,
    suggestion: str | None = None,
    console: Console | None = None,
) -> None:
    """Render a helpful empty-state message when no items or records exist."""
    cons = console or Console()
    th = get_theme()
    hint_text = hint or suggestion
    msg_text = message or ""

    lines = [f"[bold yellow]{title}[/bold yellow]"]
    if msg_text:
        lines.append(f"[dim]{msg_text}[/dim]")
    if hint_text:
        lines.append(f"\n[dim]* Hint: [bold {th.primary}]{hint_text}[/bold {th.primary}][/dim]")

    panel = Panel(
        "\n".join(lines),
        border_style="dim",
        padding=(0, 1),
    )
    cons.print(panel)
