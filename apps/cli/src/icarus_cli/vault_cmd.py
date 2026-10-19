"""CLI commands for managing server-side BYOK model provider credentials."""

from __future__ import annotations

import asyncio
from typing import Annotated

import httpx
import typer
from icarus_core.config import ConfigManager
from rich.console import Console
from rich.table import Table

from icarus_cli.remote import RemoteAgentClient

vault_app = typer.Typer(
    name="vault",
    help="Manage server-side BYOK model provider credentials.",
    no_args_is_help=True,
    rich_markup_mode="rich",
)
console = Console()


def resolve_remote_client(server: str | None = None) -> RemoteAgentClient:
    """Resolve RemoteAgentClient for targeted or active server profile."""
    cfg_mgr = ConfigManager()
    active_server = cfg_mgr.get_active_server()
    target_profile = cfg_mgr.get_server(server) if server else active_server
    if not target_profile:
        console.print(
            "[bold red]Error:[/bold red] No remote server profile found.\n"
            "Use [bold cyan]icarus server add <name> <url>[/bold cyan] "
            "or pass [bold cyan]--server <name>[/bold cyan]."
        )
        raise typer.Exit(code=1)
    api_key = cfg_mgr.get_server_api_key(target_profile.name)
    return RemoteAgentClient(base_url=target_profile.url, api_key=api_key)


def extract_error_message(exc: httpx.HTTPStatusError) -> str:
    """Extract structured error message from HTTP response envelope."""
    try:
        data = exc.response.json()
        if isinstance(data, dict):
            if "error" in data and isinstance(data["error"], dict) and "message" in data["error"]:
                return str(data["error"]["message"])
            if "detail" in data:
                return str(data["detail"])
    except Exception:
        pass
    return str(exc)


@vault_app.command(name="set")
def vault_set_cmd(
    provider: Annotated[
        str,
        typer.Argument(
            help="Provider identifier (e.g. 'openrouter', 'groq', 'anthropic', 'openai', 'grok')."
        ),
    ],
    key: Annotated[
        str | None,
        typer.Option(
            "--key",
            "-k",
            help="Plaintext model provider API key to encrypt at rest.",
        ),
    ] = None,
    server: Annotated[
        str | None,
        typer.Option("--server", "-s", help="Specific remote server profile to target."),
    ] = None,
) -> None:
    """Register or update an encrypted BYOK model provider key on the active server."""
    secret = key
    if not secret:
        secret = typer.prompt(
            f"Enter API key for provider '{provider}'",
            hide_input=True,
        )

    client = resolve_remote_client(server)
    try:
        res = asyncio.run(client.set_vault_credential(provider=provider, api_key=secret))
        console.print(
            f"[bold green]Successfully stored encrypted credential for provider "
            f"'{res.provider}' ({res.key_hint}).[/bold green]"
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


@vault_app.command(name="list")
def vault_list_cmd(
    server: Annotated[
        str | None,
        typer.Option("--server", "-s", help="Specific remote server profile to target."),
    ] = None,
) -> None:
    """Display all configured provider credentials stored in the server vault."""
    client = resolve_remote_client(server)
    try:
        creds = asyncio.run(client.list_vault_credentials())
        if not creds:
            console.print(
                "[yellow]No provider credentials configured in server vault.[/yellow]\n"
                "Use [bold cyan]icarus vault set <provider> --key <key>[/bold cyan] "
                "to register one."
            )
            return

        table = Table(
            title="[bold cyan]Server BYOK Provider Credentials[/bold cyan]",
            show_header=True,
            header_style="bold magenta",
        )
        table.add_column("Provider", style="bold white", width=18)
        table.add_column("Key Preview", style="cyan", width=20)
        table.add_column("Updated At", style="dim")

        for c in creds:
            updated_str = (
                c.updated_at.strftime("%Y-%m-%d %H:%M:%S")
                if hasattr(c.updated_at, "strftime")
                else str(c.updated_at)
            )
            table.add_row(c.provider, c.key_hint, updated_str)

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


@vault_app.command(name="remove")
def vault_remove_cmd(
    provider: Annotated[
        str,
        typer.Argument(help="Provider identifier to remove from vault (e.g. 'openrouter')."),
    ],
    server: Annotated[
        str | None,
        typer.Option("--server", "-s", help="Specific remote server profile to target."),
    ] = None,
) -> None:
    """Remove a configured model provider credential from the server vault."""
    client = resolve_remote_client(server)
    try:
        asyncio.run(client.delete_vault_credential(provider=provider))
        console.print(
            f"[bold green]Removed credential for provider '{provider}' "
            f"from server vault.[/bold green]"
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
