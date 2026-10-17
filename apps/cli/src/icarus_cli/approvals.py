"""Interactive terminal prompt and safety approval handlers for CLI."""

from __future__ import annotations

import json
from typing import TextIO

from icarus_contracts.tools import ToolCall, ToolDefinition
from icarus_core.agent.approvals import (
    ApprovalEngine,
    ApprovalPolicy,
)
from rich.console import Console
from rich.panel import Panel


def format_action_preview(tool_call: ToolCall) -> str:
    """Format a readable preview of the action being requested."""
    args = tool_call.get_arguments_dict()

    if tool_call.name == "write_file":
        path = args.get("path", "(unknown path)")
        content = str(args.get("content", ""))
        lines = content.splitlines()
        preview_lines = lines[:15]
        preview_text = "\n".join(preview_lines)
        if len(lines) > 15:
            preview_text += f"\n... ({len(lines) - 15} more lines)"

        byte_size = len(content.encode("utf-8"))
        line_count = len(lines)
        return (
            f"[bold cyan]Action:[/bold cyan] Write / Overwrite Workspace File\n"
            f"[bold cyan]Target Path:[/bold cyan] [bold white]{path}[/bold white]\n"
            f"[bold cyan]Size:[/bold cyan] {byte_size} bytes ({line_count} lines)\n\n"
            f"[bold]Content Preview:[/bold]\n"
            f"{preview_text}"
        )

    formatted_args = json.dumps(args, indent=2)
    return (
        f"[bold cyan]Tool:[/bold cyan] {tool_call.name}\n"
        f"[bold cyan]Arguments:[/bold cyan]\n{formatted_args}"
    )


def prompt_for_approval(
    tool_call: ToolCall,
    tool_definition: ToolDefinition | None = None,
    console: Console | None = None,
    stdin: TextIO | None = None,
) -> bool:
    """Display styled Rich panel with action preview and collect [y/N] confirmation."""
    cons = console or Console()
    preview_content = format_action_preview(tool_call)

    panel = Panel(
        preview_content,
        title="[bold yellow]Safety Approval Required[/bold yellow]",
        border_style="yellow",
        subtitle="[dim]This operation modifies your workspace[/dim]",
    )
    cons.print(panel)

    prompt_label = "[bold yellow]Approve execution? [y/N]: [/bold yellow]"
    try:
        if stdin is not None:
            cons.print(prompt_label, end="")
            response = stdin.readline()
        else:
            response = cons.input(prompt_label)
    except (KeyboardInterrupt, EOFError):
        cons.print("\n[dim]Approval cancelled by user.[/dim]")
        return False

    normalized = response.strip().lower()
    return normalized in ("y", "yes")


def create_cli_approval_engine(
    auto_approve: bool = False,
    console: Console | None = None,
    stdin: TextIO | None = None,
) -> ApprovalEngine:
    """Create an ApprovalEngine configured with CLI interactive prompts or auto-approve policy."""
    if auto_approve:
        return ApprovalEngine(policy=ApprovalPolicy.AUTO_APPROVE)

    cons = console or Console()

    def _callback(call: ToolCall, definition: ToolDefinition) -> bool:
        return prompt_for_approval(
            tool_call=call,
            tool_definition=definition,
            console=cons,
            stdin=stdin,
        )

    return ApprovalEngine(policy=ApprovalPolicy.INTERACTIVE, prompt_callback=_callback)
