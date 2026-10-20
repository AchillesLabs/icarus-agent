"""CLI command suite for managing external application integrations and OAuth flows."""

from __future__ import annotations

import contextlib
import json
import logging
import webbrowser
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

import typer
from icarus_contracts.integrations import AuthMethod, IntegrationManifest
from icarus_core.integrations.google import (
    DEFAULT_GOOGLE_SCOPES,
    GOOGLE_MANIFEST,
    GoogleOAuthClient,
)
from icarus_core.integrations.loopback import LoopbackCallbackServer
from icarus_core.theme import get_theme
from icarus_core.tools.auth import ToolAuthManager
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

logger = logging.getLogger("icarus.cli.integrations")
console = Console()

integrations_app = typer.Typer(
    name="integrations",
    help="Manage connected third-party integrations (Google OAuth 2.0 PKCE, Slack, GitHub, Stripe).",
    no_args_is_help=False,
)

AVAILABLE_MANIFESTS: dict[str, IntegrationManifest] = {
    "google": GOOGLE_MANIFEST,
    "github": IntegrationManifest(
        id="github",
        display_name="GitHub",
        description="Interact with GitHub repositories, pull requests, issues, and code reviews.",
        auth_method=AuthMethod.API_KEY,
        required_scopes=["repo", "read:org"],
        tools=["github_search", "github_issues", "github_create_issue"],
        required_config=["GITHUB_PERSONAL_ACCESS_TOKEN"],
        supported_modes=["local", "hosted"],
    ),
    "slack": IntegrationManifest(
        id="slack",
        display_name="Slack",
        description="Read channel messages and send updates or alerts to Slack channels.",
        auth_method=AuthMethod.API_KEY,
        required_scopes=["chat:write", "channels:read"],
        tools=["slack_send_message"],
        required_config=["SLACK_BOT_TOKEN"],
        supported_modes=["local", "hosted"],
    ),
    "stripe": IntegrationManifest(
        id="stripe",
        display_name="Stripe Payments",
        description="Inspect customer balances, subscriptions, invoices, and charges.",
        auth_method=AuthMethod.API_KEY,
        required_scopes=["read_only"],
        tools=["stripe_customer_info"],
        required_config=["STRIPE_SECRET_KEY"],
        supported_modes=["local", "hosted"],
    ),
}


def _get_google_stored_data() -> dict[str, Any] | None:
    """Retrieve and parse local Google credential JSON if present."""
    raw = ToolAuthManager.get_token("google")
    if not raw:
        return None
    raw_str = raw.strip()
    if raw_str.startswith("{"):
        try:
            parsed = json.loads(raw_str)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass
    return {"access_token": raw_str}


@integrations_app.callback(invoke_without_command=True)
def default_integrations(ctx: typer.Context) -> None:
    """Show integrations list if no subcommand is provided."""
    if ctx.invoked_subcommand is None:
        list_integrations()


@integrations_app.command(name="list", help="List supported and connected external integrations.")
def list_integrations() -> None:
    """Display table of available integrations and their current connection status."""
    th = get_theme()
    table = Table(
        title="External Integrations",
        show_header=True,
        header_style=f"bold {th.primary}",
    )
    table.add_column("Provider ID", style=f"bold {th.secondary}", width=14)
    table.add_column("Display Name", style="bold white", width=24)
    table.add_column("Auth Type", width=14)
    table.add_column("Status", width=16)
    table.add_column("Available Tools")

    for prov_id, manifest in AVAILABLE_MANIFESTS.items():
        is_connected = False
        if prov_id == "google":
            is_connected = bool(_get_google_stored_data())
        else:
            is_connected = ToolAuthManager.has_token(prov_id)

        if is_connected:
            status = "[bold green]● Connected[/bold green]"
        else:
            status = "[dim]○ Available[/dim]"

        auth_label = (
            "OAuth 2.0 PKCE" if manifest.auth_method == AuthMethod.OAUTH2_PKCE else "API Token"
        )
        tools_str = ", ".join(manifest.tools) if manifest.tools else "[dim]None[/dim]"

        table.add_row(manifest.id, manifest.display_name, auth_label, status, tools_str)

    console.print(table)
    console.print(
        f"\n[dim]* Connect an integration: [bold {th.primary}]icarus integrations connect <id>[/bold {th.primary}][/dim]"
    )
    console.print(
        f"[dim]* Example: [bold {th.primary}]icarus integrations connect google[/bold {th.primary}][/dim]\n"
    )


@integrations_app.command(
    name="connect", help="Connect an integration via OAuth 2.0 PKCE or token prompt."
)
def connect_integration(
    provider: Annotated[
        str, typer.Argument(help="Integration provider ID (e.g. 'google', 'github', 'slack')")
    ],
) -> None:
    """Authenticate and connect an integration with secure local credential storage."""
    th = get_theme()
    provider_key = provider.lower().strip()

    if provider_key not in AVAILABLE_MANIFESTS:
        console.print(f"[bold red]Error:[/bold red] Unknown integration provider '{provider}'.")
        console.print(
            "[dim]Supported providers: " + ", ".join(AVAILABLE_MANIFESTS.keys()) + "[/dim]"
        )
        raise typer.Exit(1)

    manifest = AVAILABLE_MANIFESTS[provider_key]

    if provider_key == "google":
        oauth_client = GoogleOAuthClient()
        if not oauth_client.is_configured():
            panel = Panel(
                "[bold yellow]Google OAuth 2.0 Credentials Missing[/bold yellow]\n\n"
                "To authenticate with Google Calendar, Gmail, and Drive, you need a Google OAuth Client ID.\n\n"
                "[bold cyan]Setup Instructions:[/bold cyan]\n"
                "1. Go to Google Cloud Console: [bold underline blue]https://console.cloud.google.com/apis/credentials[/bold underline blue]\n"
                "2. Create an [bold white]OAuth 2.0 Client ID[/bold white] with type [bold white]Desktop App[/bold white]\n"
                "3. Set the environment variable in your terminal or .env:\n"
                '   [bold green]export GOOGLE_CLIENT_ID="your-client-id.apps.googleusercontent.com"[/bold green]\n'
                '   [dim](Optional: export GOOGLE_CLIENT_SECRET="your-secret")[/dim]\n\n'
                "[dim]Once set, rerun: `icarus integrations connect google`[/dim]",
                title="[bold yellow]Google OAuth Setup[/bold yellow]",
                border_style="yellow",
            )
            console.print(panel)
            raise typer.Exit(1)

        server = LoopbackCallbackServer(expected_state="", timeout=120.0)
        try:
            redirect_uri = server.start()
            auth_url, state, code_verifier = oauth_client.create_authorization_flow(
                redirect_uri=redirect_uri,
                scopes=DEFAULT_GOOGLE_SCOPES,
            )
            server.expected_state = state

            console.print(
                f"\n[bold {th.primary}]Initiating Google OAuth 2.0 (PKCE)...[/bold {th.primary}]"
            )
            console.print(
                "[dim]Opening authorization consent screen in your default browser...[/dim]"
            )
            console.print(f"👉 [bold underline blue]{auth_url}[/bold underline blue]\n")

            with contextlib.suppress(Exception):
                webbrowser.open(auth_url)

            console.print("[cyan]Waiting for authorization in browser (timeout: 120s)...[/cyan]")
            code = server.wait_for_code()

            console.print("[dim]Exchanging authorization code for OAuth tokens...[/dim]")
            token_payload = oauth_client.exchange_code(
                code=code,
                redirect_uri=redirect_uri,
                code_verifier=code_verifier,
            )

            # Retrieve account email
            email = (
                oauth_client.get_account_email(token_payload.get("access_token", ""))
                or "Connected Account"
            )

            # Compute expiration timestamp
            expires_in = token_payload.get("expires_in", 3600)
            token_payload["expires_at"] = (
                datetime.now(UTC) + timedelta(seconds=int(expires_in))
            ).isoformat()
            token_payload["account_email"] = email

            # Encrypt and store locally
            ToolAuthManager.save_token("google", json.dumps(token_payload))

            success_panel = Panel(
                f"[bold green]✔ Successfully connected Google account: [bold white]{email}[/bold white][/bold green]\n\n"
                f"[bold cyan]Active Integrations & Tools:[/bold cyan]\n"
                f"• [bold white]Google Calendar[/bold white]: calendar_events, calendar_create_event\n"
                f"• [bold white]Gmail[/bold white]: gmail_search, gmail_send\n"
                f"• [bold white]Google Drive[/bold white]: drive_search, drive_read_file\n\n"
                f"[dim]Tokens are encrypted at rest with machine-local AES-Fernet encryption.[/dim]",
                title="[bold green]Google Connected[/bold green]",
                border_style="green",
            )
            console.print(success_panel)

        except TimeoutError:
            console.print(
                "[bold red]Connection timed out.[/bold red] Authorization was not completed in the browser."
            )
            raise typer.Exit(1) from None
        except Exception as exc:
            console.print(f"[bold red]Authorization failed:[/bold red] {exc}")
            raise typer.Exit(1) from exc
        finally:
            server.shutdown()

    else:
        # Standard token prompt
        token = ToolAuthManager.prompt_authorization(provider_key, console=console)
        if token:
            console.print(
                f"[bold green]✔ Successfully connected {manifest.display_name}![/bold green]"
            )
        else:
            console.print("[yellow]Connection skipped or cancelled.[/yellow]")


@integrations_app.command(
    name="status", help="Inspect connection status, account email, and granted scopes."
)
def status_integration(
    provider: Annotated[
        str | None, typer.Argument(help="Integration provider ID (default: google)")
    ] = "google",
) -> None:
    """Inspect integration health and configuration details without exposing secret tokens."""
    th = get_theme()
    provider_key = (provider or "google").lower().strip()

    if provider_key not in AVAILABLE_MANIFESTS:
        console.print(f"[bold red]Error:[/bold red] Unknown provider '{provider}'.")
        raise typer.Exit(1)

    manifest = AVAILABLE_MANIFESTS[provider_key]

    if provider_key == "google":
        stored = _get_google_stored_data()
        if not stored:
            console.print("[yellow]Google Workspace is not connected.[/yellow]")
            console.print("[dim]Run `icarus integrations connect google` to connect.[/dim]")
            return

        email = stored.get("account_email") or "Authorized User"
        expires_at = stored.get("expires_at", "Unknown")
        has_refresh = bool(stored.get("refresh_token"))

        panel = Panel(
            f"[bold white]Provider:[/bold white] Google Workspace\n"
            f"[bold white]Account:[/bold white] {email}\n"
            f"[bold white]Status:[/bold white] [bold green]● Connected (Active)[/bold green]\n"
            f"[bold white]Expires At:[/bold white] {expires_at}\n"
            f"[bold white]Refresh Token Present:[/bold white] {'Yes' if has_refresh else 'No'}\n"
            f"[bold white]Scopes:[/bold white]\n"
            + "\n".join(f"  • {s}" for s in manifest.required_scopes)
            + f"\n\n[bold white]Active Tools:[/bold white] {', '.join(manifest.tools)}",
            title=f"[bold {th.primary}]Google Workspace Connection Status[/bold {th.primary}]",
            border_style="cyan",
        )
        console.print(panel)

    else:
        has_token = ToolAuthManager.has_token(provider_key)
        status_str = (
            "[bold green]● Connected[/bold green]" if has_token else "[dim]○ Not Connected[/dim]"
        )
        panel = Panel(
            f"[bold white]Provider:[/bold white] {manifest.display_name}\n"
            f"[bold white]Status:[/bold white] {status_str}\n"
            f"[bold white]Auth Method:[/bold white] API Token\n"
            f"[bold white]Active Tools:[/bold white] {', '.join(manifest.tools)}",
            title=f"[bold {th.primary}]{manifest.display_name} Status[/bold {th.primary}]",
            border_style="cyan",
        )
        console.print(panel)


@integrations_app.command(name="disconnect", help="Revoke access and remove stored credentials.")
def disconnect_integration(
    provider: Annotated[
        str, typer.Argument(help="Integration provider ID to disconnect (e.g. 'google')")
    ],
) -> None:
    """Revoke credentials at remote provider endpoint and delete from local secure vault."""
    provider_key = provider.lower().strip()

    if provider_key not in AVAILABLE_MANIFESTS:
        console.print(f"[bold red]Error:[/bold red] Unknown provider '{provider}'.")
        raise typer.Exit(1)

    if provider_key == "google":
        stored = _get_google_stored_data()
        if stored:
            token_to_revoke = stored.get("refresh_token") or stored.get("access_token")
            if token_to_revoke:
                try:
                    client = GoogleOAuthClient()
                    client.revoke_token(token_to_revoke)
                except Exception as exc:
                    logger.debug("Google token revocation returned error: %s", exc)

        deleted = ToolAuthManager.delete_token("google")
        if deleted:
            console.print(
                "[bold green]✔ Successfully disconnected Google Workspace and purged stored credentials.[/bold green]"
            )
        else:
            console.print("[dim]Google credentials were not found or already removed.[/dim]")

    else:
        deleted = ToolAuthManager.delete_token(provider_key)
        if deleted:
            console.print(
                f"[bold green]✔ Successfully disconnected {provider_key} and purged credentials.[/bold green]"
            )
        else:
            console.print(f"[dim]No stored credentials found for {provider_key}.[/dim]")


@integrations_app.command(
    name="doctor", help="Verify integration connectivity, token freshness, and health."
)
def doctor_integration(
    provider: Annotated[
        str | None, typer.Argument(help="Integration provider ID to verify (default: google)")
    ] = "google",
) -> None:
    """Run diagnostic checks on configured integrations."""
    provider_key = (provider or "google").lower().strip()

    if provider_key == "google":
        console.print("[bold cyan]Running Google Workspace Diagnostics...[/bold cyan]\n")
        client = GoogleOAuthClient()
        if not client.is_configured():
            console.print(
                "  [bold red]✖ Client Config:[/bold red] GOOGLE_CLIENT_ID environment variable is missing."
            )
            return

        console.print("  [bold green]✔ Client Config:[/bold green] GOOGLE_CLIENT_ID configured.")

        stored = _get_google_stored_data()
        if not stored:
            console.print(
                "  [bold yellow]○ Credentials:[/bold yellow] No Google account connected. Run `icarus integrations connect google`."
            )
            return

        access_token = ToolAuthManager.get_access_token("google")
        if not access_token:
            console.print(
                "  [bold red]✖ Token Resolution:[/bold red] Failed to obtain valid access token."
            )
            return

        console.print(
            "  [bold green]✔ Credentials:[/bold green] Token found and decrypted from local vault."
        )

        # Test userinfo
        email = client.get_account_email(access_token)
        if email:
            console.print(
                f"  [bold green]✔ API Connectivity:[/bold green] Validated token with Google UserInfo endpoint ({email})."
            )
            console.print(
                "\n[bold green]All Google Workspace diagnostic checks PASSED.[/bold green]"
            )
        else:
            console.print(
                "  [bold yellow]⚠ API Connectivity:[/bold yellow] Could not verify email with Google UserInfo endpoint (token may be expired or offline)."
            )
    else:
        has_tok = ToolAuthManager.has_token(provider_key)
        if has_tok:
            console.print(
                f"[bold green]✔ {provider_key}:[/bold green] Credential present in secure vault."
            )
        else:
            console.print(f"[yellow]○ {provider_key}:[/yellow] No credentials configured.")
