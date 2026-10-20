"""CLI command suite and views for inspecting agent tools."""

from __future__ import annotations

import json
from typing import Annotated

import typer
from icarus_contracts.tools import ToolDefinition, ToolSafetyCategory
from icarus_core.theme import get_theme
from icarus_core.tools.registry import create_default_registry
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()
tools_app = typer.Typer(
    name="tools",
    help="List, inspect, and check schemas for available core and MCP tools.",
)


def render_tools_table(console: Console, filter_text: str | None = None) -> None:
    """Render a styled table of all registered tools and their safety policies."""
    registry = create_default_registry(load_mcp=True)
    tools = registry.list_tools()
    th = get_theme()

    if filter_text:
        query = filter_text.strip().lower()
        tools = [t for t in tools if query in t.name.lower() or query in (t.description or "").lower()]

    table = Table(
        title=f"Available Tools ({len(tools)} registered)",
        show_header=True,
        header_style=f"bold {th.primary}",
    )
    table.add_column("Tool Name", style=f"bold {th.secondary}", width=24)
    table.add_column("Category", width=19)
    table.add_column("Source", width=14)
    table.add_column("Description")

    for tool in tools:
        is_approval = tool.safety_category == ToolSafetyCategory.REQUIRES_APPROVAL
        cat_style = "bold yellow" if is_approval else "dim green"
        cat_label = "Requires Approval" if is_approval else "Safe (Auto)"

        if tool.name.startswith("mcp_"):
            source = "[cyan]MCP[/cyan]"
        else:
            source = "[dim]Core[/dim]"

        desc = (tool.description or "").split("\n")[0]
        if len(desc) > 60:
            desc = desc[:57] + "..."

        table.add_row(tool.name, f"[{cat_style}]{cat_label}[/{cat_style}]", source, desc)

    console.print(table)
    console.print(
        f"\n[dim]Run [bold {th.primary}]/tools <name>[/bold {th.primary}] or [bold {th.primary}]icarus tools show <name>[/bold {th.primary}] for parameters schema.[/dim]\n"
    )


def render_tool_detail(console: Console, tool_name: str) -> None:
    """Render parameter schema and documentation for a specific tool."""
    registry = create_default_registry(load_mcp=True)
    tool = registry.get(tool_name)
    th = get_theme()

    if not tool:
        console.print(f"[bold red]Error:[/bold red] Tool '[yellow]{tool_name}[/yellow]' not found.")
        console.print("[dim]Use `/tools` or `icarus tools list` to view all available tools.[/dim]")
        return

    definition = tool.definition
    is_approval = definition.safety_category == ToolSafetyCategory.REQUIRES_APPROVAL
    cat_style = "bold yellow" if is_approval else "bold green"
    cat_label = "REQUIRES APPROVAL (Interactive [y/N] prompt)" if is_approval else "SAFE READ (Auto-approved)"

    props = definition.parameters.get("properties", {}) if isinstance(definition.parameters, dict) else {}
    required = set(definition.parameters.get("required", [])) if isinstance(definition.parameters, dict) else set()

    param_table = Table(title="Parameters Schema", show_header=True, header_style=f"bold {th.primary}")
    param_table.add_column("Parameter", style=f"bold {th.secondary}", width=18)
    param_table.add_column("Type", width=10)
    param_table.add_column("Required", width=10)
    param_table.add_column("Description")

    if props:
        for p_name, p_info in props.items():
            p_type = p_info.get("type", "any") if isinstance(p_info, dict) else "any"
            p_desc = p_info.get("description", "") if isinstance(p_info, dict) else ""
            is_req = "Yes" if p_name in required else "No"
            req_styled = "[bold red]Yes[/bold red]" if is_req == "Yes" else "[dim]No[/dim]"
            param_table.add_row(p_name, p_type, req_styled, p_desc)
    else:
        param_table.add_row("[dim]None[/dim]", "-", "-", "Tool takes no parameters")

    meta_text = (
        f"[bold {th.primary}]Tool Name:[/bold {th.primary}] [bold white]{definition.name}[/bold white]\n"
        f"[bold {th.primary}]Safety:[/bold {th.primary}] [{cat_style}]{cat_label}[/{cat_style}]\n"
        f"[bold {th.primary}]Description:[/bold {th.primary}] {definition.description}\n"
    )

    console.print(Panel(meta_text, border_style=th.border, title=f"[bold {th.secondary}]Tool Details: {definition.name}[/bold {th.secondary}]"))
    console.print(param_table)
    console.print()


@tools_app.command(name="list")
def list_tools(
    filter_text: Annotated[str | None, typer.Argument(help="Optional keyword filter.")] = None,
) -> None:
    """List all registered tools (core and MCP) with their safety categories."""
    render_tools_table(console, filter_text=filter_text)


@tools_app.command(name="show")
def show_tool(
    name: Annotated[str, typer.Argument(help="Name of the tool to inspect.")],
) -> None:
    """Inspect parameters schema and description for a specific tool."""
    render_tool_detail(console, tool_name=name)
