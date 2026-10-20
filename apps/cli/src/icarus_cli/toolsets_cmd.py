"""CLI command suite for inspecting and managing modular toolsets."""

from __future__ import annotations

from typing import Annotated

import typer
from icarus_core.theme import get_theme
from icarus_core.tools.toolsets import ToolsetManager
from rich.console import Console
from rich.table import Table

console = Console()
toolsets_app = typer.Typer(
    name="toolsets",
    help="Manage modular toolsets (enable/disable tool categories).",
    no_args_is_help=False,
)


@toolsets_app.callback(invoke_without_command=True)
def default_toolsets(ctx: typer.Context) -> None:
    """Show toolsets list when no subcommand is given."""
    if ctx.invoked_subcommand is None:
        list_toolsets()


@toolsets_app.command(name="list", help="List all available toolsets and their active status.")
def list_toolsets() -> None:
    """Render a styled table of toolsets, their status, tags, and tools."""
    mgr = ToolsetManager()
    toolsets = mgr.list_toolsets()
    active_toolsets = mgr.load_active_toolsets()
    th = get_theme()

    table = Table(
        title=f"Modular Toolsets ({len(active_toolsets)}/{len(toolsets)} enabled)",
        show_header=True,
        header_style=f"bold {th.primary}",
    )
    table.add_column("Toolset", style=f"bold {th.secondary}", width=15)
    table.add_column("Display Name", style="bold white", width=22)
    table.add_column("Status", width=14)
    table.add_column("Tags", width=16)
    table.add_column("Included Tools")

    for ts in toolsets:
        is_enabled = ts.name in active_toolsets
        status = (
            "[bold green]● Enabled[/bold green]" if is_enabled else "[dim red]○ Disabled[/dim red]"
        )
        tags = ", ".join(ts.tags)
        tools = ", ".join(ts.tools)

        table.add_row(ts.name, ts.display_name, status, tags, tools)

    console.print(table)
    console.print(
        f"\n[dim]* Enable a toolset: [bold {th.primary}]icarus toolsets enable <name>[/bold {th.primary}][/dim]"
    )
    console.print(
        f"[dim]* Disable a toolset: [bold {th.primary}]icarus toolsets disable <name>[/bold {th.primary}][/dim]\n"
    )


@toolsets_app.command(name="enable", help="Enable a toolset category.")
def enable_toolset(
    name: Annotated[
        str, typer.Argument(help="Name of the toolset to enable (e.g. 'integrations', 'web')")
    ],
) -> None:
    """Enable a toolset category."""
    mgr = ToolsetManager()
    ts_name = name.lower().strip()
    ts = mgr.get_toolset(ts_name)
    if not ts:
        console.print(f"[bold red]Error:[/bold red] Unknown toolset '{name}'.")
        console.print("[dim]Run `icarus toolsets list` to see available toolsets.[/dim]")
        raise typer.Exit(1)

    mgr.enable_toolset(ts_name)
    console.print(
        f"[bold green]✔ Toolset '{ts.display_name}' ({ts_name}) is now ENABLED.[/bold green]"
    )


@toolsets_app.command(name="disable", help="Disable a toolset category.")
def disable_toolset(
    name: Annotated[
        str, typer.Argument(help="Name of the toolset to disable (e.g. 'terminal', 'mcp')")
    ],
) -> None:
    """Disable a toolset category."""
    mgr = ToolsetManager()
    ts_name = name.lower().strip()
    ts = mgr.get_toolset(ts_name)
    if not ts:
        console.print(f"[bold red]Error:[/bold red] Unknown toolset '{name}'.")
        console.print("[dim]Run `icarus toolsets list` to see available toolsets.[/dim]")
        raise typer.Exit(1)

    mgr.disable_toolset(ts_name)
    console.print(f"[yellow]✔ Toolset '{ts.display_name}' ({ts_name}) is now DISABLED.[/yellow]")


@toolsets_app.command(name="reset", help="Reset all toolsets to default enabled configuration.")
def reset_toolsets() -> None:
    """Reset toolsets to factory defaults."""
    mgr = ToolsetManager()
    mgr.reset_defaults()
    console.print("[bold green]✔ Toolsets have been reset to default configuration.[/bold green]")
