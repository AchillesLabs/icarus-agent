"""CLI commands for inspecting, previewing, and setting UI color themes."""

from typing import Annotated

import typer
from icarus_core.theme import get_theme, list_themes, set_theme
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

theme_app = typer.Typer(
    name="theme",
    help="Customize, preview, and set the UI accent color theme.",
    rich_markup_mode="rich",
    no_args_is_help=False,
)

console = Console()


@theme_app.callback(invoke_without_command=True)
def list_or_set_theme(
    ctx: typer.Context,
    name: Annotated[
        str | None,
        typer.Argument(
            help="Name of theme (purple, cyan, green, amber, red, blue, pink) or custom hex (#RRGGBB)."
        ),
    ] = None,
) -> None:
    """List available themes or switch the active UI theme."""
    if ctx.invoked_subcommand is not None:
        return

    if name:
        try:
            new_theme = set_theme(name)
            console.print(
                f"\n[bold green]✔ Successfully set UI theme to[/bold green] [bold {new_theme.primary}]'{new_theme.name}'[/bold {new_theme.primary}]!"
            )
            preview_panel = Panel(
                f"[{new_theme.primary}]Primary: {new_theme.primary}[/{new_theme.primary}]\n"
                f"[{new_theme.border}]Border: {new_theme.border}[/{new_theme.border}]\n"
                f"[{new_theme.secondary}]Secondary: {new_theme.secondary}[/{new_theme.secondary}]",
                title=f"[bold {new_theme.secondary}]Theme Preview[/bold {new_theme.secondary}]",
                border_style=new_theme.border,
            )
            console.print(preview_panel)
            console.print(
                "[dim]The new theme will be used in your next Icarus chat session and commands.[/dim]\n"
            )
        except Exception as exc:
            console.print(f"[bold red]Error setting theme:[/bold red] {exc}")
            raise typer.Exit(code=1) from exc
        return

    active_theme = get_theme()
    themes = list_themes()

    table = Table(
        title="Icarus UI Color Themes",
        show_header=True,
        header_style=f"bold {active_theme.primary}",
    )
    table.add_column("Theme", style="bold", width=14)
    table.add_column("Preview Swatch", width=18)
    table.add_column("Primary Hex", width=14)
    table.add_column("Description")
    table.add_column("Status", width=12)

    for th_name, th in themes.items():
        is_active = th_name == active_theme.name
        status = "[bold green]✔ active[/bold green]" if is_active else "[dim]available[/dim]"
        swatch = f"[{th.primary}]█████████[/{th.primary}]"
        table.add_row(
            f"[{th.primary}]{th.name}[/{th.primary}]",
            swatch,
            th.primary,
            th.description,
            status,
        )

    console.print()
    console.print(table)
    console.print(
        f"[dim]* To switch theme: [bold {active_theme.primary}]icarus theme <name_or_hex>[/bold {active_theme.primary}] (e.g. icarus theme cyan or icarus theme #FF007F)[/dim]\n"
        f"[dim]* Or in chat: [bold {active_theme.primary}]/theme <name_or_hex>[/bold {active_theme.primary}][/dim]\n"
    )


@theme_app.command(name="set")
def set_theme_cmd(
    name: Annotated[
        str,
        typer.Argument(
            help="Name of theme (purple, cyan, green, amber, red, blue, pink) or custom hex (#RRGGBB)."
        ),
    ],
) -> None:
    """Set the active UI accent color theme."""
    try:
        new_theme = set_theme(name)
        console.print(
            f"\n[bold green]✔ Successfully set UI theme to[/bold green] [bold {new_theme.primary}]'{new_theme.name}'[/bold {new_theme.primary}]!"
        )
        preview_panel = Panel(
            f"[{new_theme.primary}]Primary: {new_theme.primary}[/{new_theme.primary}]\n"
            f"[{new_theme.border}]Border: {new_theme.border}[/{new_theme.border}]\n"
            f"[{new_theme.secondary}]Secondary: {new_theme.secondary}[/{new_theme.secondary}]",
            title=f"[bold {new_theme.secondary}]Theme Preview[/bold {new_theme.secondary}]",
            border_style=new_theme.border,
        )
        console.print(preview_panel)
    except Exception as exc:
        console.print(f"[bold red]Error setting theme:[/bold red] {exc}")
        raise typer.Exit(code=1) from exc
