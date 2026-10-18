"""CLI commands for managing remote Icarus API server connection profiles."""

from typing import Annotated

import typer
from icarus_core.config import ConfigManager
from rich.console import Console
from rich.table import Table

server_app = typer.Typer(
    name="server",
    help="Manage remote Icarus API server connection profiles and active targets.",
    no_args_is_help=True,
    rich_markup_mode="rich",
)
console = Console()


@server_app.command(name="add")
def add_server_cmd(
    name: Annotated[
        str,
        typer.Argument(
            help="Unique identifier name for the remote server profile (e.g. 'production')."
        ),
    ],
    url: Annotated[
        str,
        typer.Argument(
            help="Base HTTP/HTTPS URL of the remote API service (e.g. 'https://api.icarus.ai')."
        ),
    ],
    key: Annotated[
        str | None,
        typer.Option("--key", "-k", help="Optional Bearer authentication token or API key."),
    ] = None,
    activate: Annotated[
        bool,
        typer.Option(
            "--activate/--no-activate",
            help="Set this server as the currently active remote target.",
        ),
    ] = True,
) -> None:
    """Register a new remote Icarus API server connection profile."""
    cfg_mgr = ConfigManager()
    profile = cfg_mgr.add_server(name=name, url=url, api_key=key, active=activate)
    status_msg = "[bold green]active[/bold green]" if profile.active else "[dim]inactive[/dim]"
    console.print(
        f"[bold green]Added remote server profile '{name}' ({url}) as {status_msg}.[/bold green]"
    )


@server_app.command(name="list")
def list_servers_cmd() -> None:
    """Display all configured remote server connection profiles."""
    cfg_mgr = ConfigManager()
    servers = cfg_mgr.list_servers()

    if not servers:
        console.print(
            "[yellow]No remote server profiles configured.[/yellow]\n"
            "Use [bold cyan]icarus server add <name> <url>[/bold cyan] "
            "to register a remote profile."
        )
        return

    table = Table(
        title="[bold cyan]Configured Remote Icarus Servers[/bold cyan]",
        show_header=True,
        header_style="bold magenta",
    )
    table.add_column("Status", justify="center", width=10)
    table.add_column("Name", style="bold white", width=18)
    table.add_column("URL", style="cyan")
    table.add_column("Auth", justify="center", width=12)

    for s in servers:
        status_badge = "[bold green]ACTIVE[/bold green]" if s.active else "[dim]inactive[/dim]"
        api_key = cfg_mgr.get_server_api_key(s.name)
        auth_badge = "[green]Token Set[/green]" if api_key else "[dim]None[/dim]"
        table.add_row(
            status_badge,
            s.name,
            s.url,
            auth_badge,
        )

    console.print(table)


@server_app.command(name="switch")
def switch_server_cmd(
    name: Annotated[
        str,
        typer.Argument(help="Name of the remote server profile to activate."),
    ],
) -> None:
    """Switch the active remote server profile."""
    cfg_mgr = ConfigManager()
    try:
        profile = cfg_mgr.switch_server(name)
        console.print(
            f"[bold green]Switched active remote server to '{profile.name}' "
            f"({profile.url}).[/bold green]"
        )
    except KeyError:
        console.print(f"[bold red]Error:[/bold red] Server profile '{name}' not found.")
        raise typer.Exit(code=1) from None


@server_app.command(name="remove")
def remove_server_cmd(
    name: Annotated[
        str,
        typer.Argument(help="Name of the remote server profile to remove."),
    ],
) -> None:
    """Remove a configured remote server profile."""
    cfg_mgr = ConfigManager()
    if cfg_mgr.remove_server(name):
        console.print(f"[bold green]Removed remote server profile '{name}'.[/bold green]")
    else:
        console.print(f"[bold red]Error:[/bold red] Server profile '{name}' not found.")
        raise typer.Exit(code=1)
