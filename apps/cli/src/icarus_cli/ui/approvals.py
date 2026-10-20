"""Interactive approval prompts and safety review dialogues for Icarus tools."""

from __future__ import annotations

import json
from typing import TextIO

from icarus_contracts.tools import ToolCall, ToolDefinition
from rich.console import Console
from rich.panel import Panel


def format_action_preview(tool_call: ToolCall) -> str:
    """Format a detailed preview of the action being requested."""
    args = tool_call.get_arguments_dict()
    name = tool_call.name.lower()

    if name == "run_command" or name in ("bash", "sh", "terminal", "exec"):
        cmd = str(args.get("command") or args.get("cmd") or "(unknown command)")
        cwd = str(args.get("cwd") or ".")
        timeout = args.get("timeout", 30.0)
        return (
            f"[bold cyan]Action:[/bold cyan] Execute Shell Command\n"
            f"[bold cyan]Tool:[/bold cyan] {tool_call.name}\n"
            f"[bold cyan]Command:[/bold cyan] [bold white]{cmd}[/bold white]\n"
            f"[bold cyan]Directory:[/bold cyan] {cwd}\n"
            f"[bold cyan]Timeout:[/bold cyan] {timeout}s\n\n"
            f"[yellow]This action executes a local command on your system.[/yellow]\n"
            f"[dim]Verify the command before approving.[/dim]"
        )

    if name in ("write_file", "write_to_file", "replace_file_content"):
        path = str(args.get("path") or args.get("TargetFile") or "(unknown path)")
        content = str(args.get("content") or args.get("CodeContent") or "")
        lines = content.splitlines()
        preview_lines = lines[:15]
        preview_text = "\n".join(preview_lines)
        if len(lines) > 15:
            preview_text += f"\n... ({len(lines) - 15} more lines)"

        byte_size = len(content.encode("utf-8"))
        line_count = len(lines)
        return (
            f"[bold cyan]Tool:[/bold cyan] {tool_call.name}\n"
            f"[bold cyan]Target Path:[/bold cyan] [bold white]{path}[/bold white]\n"
            f"[bold cyan]Size:[/bold cyan] {byte_size} bytes ({line_count} lines)\n\n"
            f"[bold]Content Preview:[/bold]\n"
            f"{preview_text}\n\n"
            f"[yellow]This action modifies or overwrites a file on your disk.[/yellow]"
        )

    if any(
        k in name
        for k in ("pay", "purchase", "charge", "transfer", "checkout", "transaction", "stripe")
    ):
        lines = [
            "[bold red]CRITICAL FINANCIAL / PAYMENT ACTION[/bold red]",
            f"[bold cyan]Tool:[/bold cyan] [bold white]{tool_call.name}[/bold white]",
        ]
        for key, val in args.items():
            lines.append(f"[bold yellow]{key}:[/bold yellow] {val}")
        lines.append(
            "\n[bold red]Verify the payment amount and recipient carefully before approving.[/bold red]"
        )
        return "\n".join(lines)

    if any(k in name for k in ("book", "reserve", "ticket", "flight", "hotel")):
        lines = [
            "[bold green]BOOKING / RESERVATION ACTION[/bold green]",
            f"[bold cyan]Tool:[/bold cyan] [bold white]{tool_call.name}[/bold white]",
        ]
        for key, val in args.items():
            lines.append(f"[bold cyan]{key}:[/bold cyan] {val}")
        lines.append("\n[dim]Confirm booking details and pricing before proceeding.[/dim]")
        return "\n".join(lines)

    if any(k in name for k in ("schedule", "calendar", "event", "meeting", "invite")):
        lines = [
            "[bold magenta]CALENDAR / SCHEDULING ACTION[/bold magenta]",
            f"[bold cyan]Tool:[/bold cyan] [bold white]{tool_call.name}[/bold white]",
        ]
        for key, val in args.items():
            lines.append(f"[bold cyan]{key}:[/bold cyan] {val}")
        lines.append("\n[dim]Confirm date, attendees, and schedule details.[/dim]")
        return "\n".join(lines)

    if any(k in name for k in ("send_email", "send_message", "slack_send", "gmail_send")):
        lines = [
            "[bold blue]EXTERNAL COMMUNICATION ACTION[/bold blue]",
            f"[bold cyan]Tool:[/bold cyan] [bold white]{tool_call.name}[/bold white]",
        ]
        for key, val in args.items():
            lines.append(f"[bold cyan]{key}:[/bold cyan] {val}")
        lines.append("\n[dim]This action transmits messages externally.[/dim]")
        return "\n".join(lines)

    formatted_args = json.dumps(args, indent=2)
    return (
        f"[bold cyan]Tool:[/bold cyan] {tool_call.name}\n"
        f"[bold cyan]Arguments:[/bold cyan]\n{formatted_args}\n\n"
        f"[dim]Verify action parameters before approving.[/dim]"
    )


def prompt_for_approval(
    tool_call: ToolCall,
    tool_definition: ToolDefinition | None = None,
    console: Console | None = None,
    stdin: TextIO | None = None,
) -> bool:
    """Display styled approval box and collect strict [y/N] user confirmation.

    Defaults strictly to denial on empty input, non-matching input, or EOF/Interrupt.
    """
    cons = console or Console()
    preview_content = format_action_preview(tool_call)

    name_lower = tool_call.name.lower()
    if any(
        k in name_lower
        for k in ("pay", "purchase", "charge", "transfer", "checkout", "transaction")
    ):
        title = (
            "[bold red]ACTION REQUIRES APPROVAL (Financial Payment Approval Required)[/bold red]"
        )
        border_style = "red"
        subtitle = "[bold yellow]Verify amount, recipient, and authorization[/bold yellow]"
    elif any(k in name_lower for k in ("book", "reserve", "ticket", "flight", "hotel")):
        title = "[bold green]ACTION REQUIRES APPROVAL (Booking / Reservation Approval Required)[/bold green]"
        border_style = "green"
        subtitle = "[dim]Confirm booking details and pricing[/dim]"
    elif any(k in name_lower for k in ("schedule", "calendar", "event", "meeting", "invite")):
        title = "[bold magenta]ACTION REQUIRES APPROVAL (Calendar / Schedule Approval Required)[/bold magenta]"
        border_style = "magenta"
        subtitle = "[dim]Confirm date, attendees, and calendar modifications[/dim]"
    else:
        title = "[bold yellow]ACTION REQUIRES APPROVAL (Safety Approval Required)[/bold yellow]"
        border_style = "yellow"
        subtitle = "[dim]This operation modifies your workspace or environment[/dim]"

    panel = Panel(
        preview_content,
        title=title,
        border_style=border_style,
        subtitle=subtitle,
        padding=(0, 1),
    )
    cons.print(panel)

    prompt_label = "[bold yellow]Allow this action? [y/N]: [/bold yellow]"
    try:
        if stdin is not None:
            cons.print(prompt_label, end="")
            response = stdin.readline()
        else:
            response = cons.input(prompt_label)
    except (KeyboardInterrupt, EOFError):
        cons.print("\n[dim]Action approval denied or cancelled by user.[/dim]")
        return False

    normalized = response.strip().lower()
    # Strict confirmation: ONLY 'y' or 'yes' approves. Everything else defaults to denial.
    return normalized in ("y", "yes")


render_approval_prompt = prompt_for_approval
