"""CLI commands for managing remote Icarus API tokens."""

from __future__ import annotations

import asyncio
from typing import Annotated

import httpx
import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from icarus_cli.vault_cmd import extract_error_message, resolve_remote_client

token_app = typer.Typer(
    name="token",
    help="Manage remote API access tokens.",
    no_args_is_help=True,
    rich_markup_mode="rich",
)
console = Console()


@token_app.command(name="create")
def token_create_cmd(
    name: Annotated[
        str,
        typer.Argument(help="Friendly name or label for the API token (e.g. 'ci-runner')."),
    ],
    server: Annotated[
        str | None,
        typer.Option("--server", "-s", help="Specific remote server profile to target."),
    ] = None,
) -> None:
    """Generate and safely display a new remote API token."""
    client = resolve_remote_client(server)
    try:
        token = asyncio.run(client.create_api_token(name=name))
        created_str = (
            token.created_at.strftime("%Y-%m-%d %H:%M:%S")
            if hasattr(token.created_at, "strftime")
            else str(token.created_at)
        )
        token_info = (
            f"[bold green]API Token Created Successfully![/bold green]\n\n"
            f"[bold white]Name:[/bold white] {token.name}\n"
            f"[bold white]ID:[/bold white] [dim]{token.id}[/dim]\n"
            f"[bold white]Prefix:[/bold white] [cyan]{token.prefix}[/cyan]\n"
            f"[bold white]Created:[/bold white] {created_str}\n\n"
            f"[bold yellow]Token Secret:[/bold yellow]\n"
            f"[bold green]{token.token}[/bold green]\n\n"
            f"[bold red]WARNING:[/bold red] Make sure to copy your personal access token now.\n"
            f"You won't be able to see it again!"
        )
        panel = Panel(
            token_info,
            title="[bold cyan]Icarus API Token[/bold cyan]",
            border_style="cyan",
        )
        console.print(panel)
    except httpx.HTTPStatusError as exc:
        msg = extract_error_message(exc)
        console.print(f"[bold red]Error:[/bold red] {msg}")
        raise typer.Exit(code=1) from None
    except Exception as exc:
        console.print(f"[bold red]Remote error:[/bold red] {exc}")
        raise typer.Exit(code=1) from exc
    finally:
        asyncio.run(client.close())


@token_app.command(name="list")
def token_list_cmd(
    all_tokens: Annotated[
        bool,
        typer.Option(
            "--all/--active-only",
            "-a",
            help="Include revoked and inactive tokens in the output.",
        ),
    ] = True,
    server: Annotated[
        str | None,
        typer.Option("--server", "-s", help="Specific remote server profile to target."),
    ] = None,
) -> None:
    """Display active and revoked tokens for the authenticated tenant."""
    client = resolve_remote_client(server)
    try:
        tokens = asyncio.run(client.list_api_tokens(include_revoked=all_tokens))
        if not tokens:
            console.print(
                "[yellow]No API tokens found on remote server.[/yellow]\n"
                "Use [bold cyan]icarus token create <name>[/bold cyan] to issue one."
            )
            return

        table = Table(
            title="[bold cyan]Remote API Access Tokens[/bold cyan]",
            show_header=True,
            header_style="bold magenta",
        )
        table.add_column("Status", justify="center")
        table.add_column("ID", style="dim")
        table.add_column("Name", style="bold white")
        table.add_column("Prefix", style="cyan")
        table.add_column("Last Used", style="dim")
        table.add_column("Created", style="dim")

        for t in tokens:
            status_badge = (
                "[bold green]ACTIVE[/bold green]" if t.is_active else "[bold red]REVOKED[/bold red]"
            )
            last_used_str = (
                t.last_used_at.strftime("%Y-%m-%d %H:%M:%S")
                if t.last_used_at and hasattr(t.last_used_at, "strftime")
                else (str(t.last_used_at) if t.last_used_at else "[dim]Never[/dim]")
            )
            created_str = (
                t.created_at.strftime("%Y-%m-%d %H:%M:%S")
                if hasattr(t.created_at, "strftime")
                else str(t.created_at)
            )
            table.add_row(
                status_badge,
                t.id,
                t.name,
                t.prefix,
                last_used_str,
                created_str,
            )

        console.print(table)
    except httpx.HTTPStatusError as exc:
        msg = extract_error_message(exc)
        console.print(f"[bold red]Error:[/bold red] {msg}")
        raise typer.Exit(code=1) from None
    except Exception as exc:
        console.print(f"[bold red]Remote error:[/bold red] {exc}")
        raise typer.Exit(code=1) from exc
    finally:
        asyncio.run(client.close())


@token_app.command(name="revoke")
def token_revoke_cmd(
    token_id: Annotated[
        str,
        typer.Argument(help="UUID of the API token to revoke."),
    ],
    server: Annotated[
        str | None,
        typer.Option("--server", "-s", help="Specific remote server profile to target."),
    ] = None,
) -> None:
    """Instantly revoke an active API token."""
    client = resolve_remote_client(server)
    try:
        revoked_token = asyncio.run(client.revoke_api_token(token_id=token_id))
        console.print(
            f"[bold green]Successfully revoked API token '{revoked_token.name}' "
            f"({revoked_token.id}).[/bold green]"
        )
    except httpx.HTTPStatusError as exc:
        msg = extract_error_message(exc)
        console.print(f"[bold red]Error:[/bold red] {msg}")
        raise typer.Exit(code=1) from None
    except Exception as exc:
        console.print(f"[bold red]Remote error:[/bold red] {exc}")
        raise typer.Exit(code=1) from exc
    finally:
        asyncio.run(client.close())
