"""View rendering utilities for session lists and transcripts in Rich format."""

from __future__ import annotations

import json
from typing import Any

from icarus_contracts.session import MessageDTO, MessageRole, SessionDTO, SessionSummaryDTO
from rich.console import Console
from rich.panel import Panel
from rich.table import Table


def render_sessions_table(
    summaries: list[SessionSummaryDTO],
    console: Console | None = None,
) -> None:
    """Render a styled Rich table of previous conversation sessions."""
    con = console or Console()
    if not summaries:
        con.print("[yellow]No previous sessions found.[/yellow]")
        return

    table = Table(
        title="[bold cyan]Icarus Conversation Sessions[/bold cyan]",
        show_header=True,
        header_style="bold magenta",
        expand=True,
    )
    table.add_column("Session ID", style="bold cyan", min_width=36)
    table.add_column("Title", style="bold white", min_width=20)
    table.add_column("Mode", style="yellow", justify="center", width=10)
    table.add_column("Messages", justify="right", style="magenta", width=10)
    table.add_column("Est. Tokens", justify="right", style="green", width=14)
    table.add_column("Last Active", style="dim", width=20)

    for s in summaries:
        date_str = (
            s.updated_at.strftime("%Y-%m-%d %H:%M")
            if hasattr(s.updated_at, "strftime")
            else str(s.updated_at)
        )
        tok_str = f"{s.total_estimated_tokens:,}" if s.total_estimated_tokens else "0"
        table.add_row(
            s.id,
            s.title,
            s.mode,
            str(s.message_count),
            tok_str,
            date_str,
        )

    con.print(table)


def render_session_history(
    session: SessionDTO,
    messages: list[MessageDTO],
    total_tokens: int = 0,
    console: Console | None = None,
) -> None:
    """Render the chronological transcript and tool calls of a specific session."""
    con = console or Console()

    # Session metadata header panel
    header_table = Table.grid(padding=(0, 2))
    header_table.add_column(style="bold cyan")
    header_table.add_column()
    header_table.add_row("ID:", f"[cyan]{session.id}[/cyan]")
    header_table.add_row("Mode:", f"[yellow]{session.mode}[/yellow]")
    created_str = (
        session.created_at.strftime("%Y-%m-%d %H:%M:%S")
        if hasattr(session.created_at, "strftime")
        else str(session.created_at)
    )
    header_table.add_row("Created:", f"[dim]{created_str}[/dim]")
    header_table.add_row("Messages:", f"[magenta]{len(messages)}[/magenta]")
    tok_display = f"{total_tokens:,}" if total_tokens else "0"
    header_table.add_row("Est. Tokens:", f"[green]{tok_display}[/green]")

    con.print(
        Panel(
            header_table,
            title=f"[bold]Session Transcript: {session.title}[/bold]",
            border_style="cyan",
            expand=False,
        )
    )
    con.print()

    if not messages:
        con.print("[dim]No messages in this session.[/dim]")
        return

    for m in messages:
        m_role = m.role.value if hasattr(m.role, "value") else str(m.role)
        tok_badge = (
            f" [dim]({m.token_estimate} tokens)[/dim]" if m.token_estimate is not None else ""
        )

        if m_role == MessageRole.USER.value or m_role == "user":
            con.print(f"[bold cyan]User > [/bold cyan]{m.content}{tok_badge}")
            con.print()

        elif m_role == MessageRole.ASSISTANT.value or m_role == "assistant":
            if m.tool_calls:
                for tc in m.tool_calls:
                    tc_name, tc_id, tc_args = _extract_tool_call_details(tc)
                    con.print(
                        f"[bold yellow]⚙ Tool Call ({tc_name})[/bold yellow] "
                        f"[dim][{tc_id}][/dim]: {tc_args}"
                    )
            if m.content:
                con.print(f"[bold green]Assistant > [/bold green]{m.content}{tok_badge}")
                con.print()

        elif m_role == MessageRole.TOOL.value or m_role == "tool":
            tool_label = m.name or m.tool_call_id or "Tool"
            con.print(f"[dim]⚙ Tool Result ({tool_label}) > {m.content}{tok_badge}[/dim]")
            con.print()

        elif m_role == MessageRole.SYSTEM.value or m_role == "system":
            con.print(f"[dim italic]📝 System / Summary > {m.content}{tok_badge}[/dim italic]")
            con.print()

        else:
            con.print(f"[dim]{m_role.capitalize()} > {m.content}{tok_badge}[/dim]")
            con.print()


def _extract_tool_call_details(tc: Any) -> tuple[str, str, str]:
    """Helper to extract (name, id, arguments_str) from a tool call object or dict."""
    if isinstance(tc, dict):
        tc_id = tc.get("id", "")
        if "function" in tc and isinstance(tc["function"], dict):
            tc_name = tc["function"].get("name", "tool")
            raw_args = tc["function"].get("arguments", "")
        else:
            tc_name = tc.get("name", "tool")
            raw_args = tc.get("arguments", "")
    else:
        tc_id = getattr(tc, "id", "")
        tc_name = getattr(tc, "name", "tool")
        raw_args = getattr(tc, "arguments", "")

    args_str = json.dumps(raw_args) if isinstance(raw_args, dict) else str(raw_args)
    return tc_name, tc_id, args_str
