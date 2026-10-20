"""CLI command suite and views for inspecting agent tools."""

from __future__ import annotations

import contextlib
from typing import Annotated

import typer
from icarus_contracts.tools import ToolSafetyCategory
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
        tools = [
            t for t in tools if query in t.name.lower() or query in (t.description or "").lower()
        ]

    from icarus_core.tools.toolsets import ToolsetManager

    mgr = ToolsetManager()
    active_toolsets = mgr.load_active_toolsets()

    table = Table(
        title=f"Available Tools ({len(tools)} registered)",
        show_header=True,
        header_style=f"bold {th.primary}",
    )
    table.add_column("Tool Name", style=f"bold {th.secondary}", width=22)
    table.add_column("Toolset", width=14)
    table.add_column("Category", width=18)
    table.add_column("Source", width=12)
    table.add_column("Description")

    for tool in tools:
        is_approval = tool.safety_category == ToolSafetyCategory.REQUIRES_APPROVAL
        cat_style = "bold yellow" if is_approval else "dim green"
        cat_label = "Requires Approval" if is_approval else "Safe (Auto)"

        if tool.name.startswith("mcp_"):
            source = "[cyan]MCP[/cyan]"
            ts_name = "mcp"
        else:
            source = "[dim]Core[/dim]"
            ts_name = "custom"
            for candidate_ts, ts_def in mgr._toolsets.items():
                if tool.name in ts_def.tools:
                    ts_name = candidate_ts
                    break

        is_ts_active = ts_name in active_toolsets if ts_name != "custom" else True
        ts_style = "cyan" if is_ts_active else "dim red strike"
        ts_display = f"[{ts_style}]{ts_name}[/{ts_style}]"

        desc = (tool.description or "").split("\n")[0]
        if len(desc) > 55:
            desc = desc[:52] + "..."

        name_display = tool.name if is_ts_active else f"[dim]{tool.name} (disabled)[/dim]"
        table.add_row(
            name_display, ts_display, f"[{cat_style}]{cat_label}[/{cat_style}]", source, desc
        )

    console.print(table)
    console.print(
        f"\n[dim]Run [bold {th.primary}]/tools <name>[/bold {th.primary}] or [bold {th.primary}]icarus tools show <name>[/bold {th.primary}] for parameters schema.[/dim]"
    )
    console.print(
        f"[dim]Run [bold {th.primary}]icarus toolsets list[/bold {th.primary}] to inspect or enable/disable toolsets.[/dim]\n"
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
    cat_label = (
        "REQUIRES APPROVAL (Interactive [y/N] prompt)"
        if is_approval
        else "SAFE READ (Auto-approved)"
    )

    props = (
        definition.parameters.get("properties", {})
        if isinstance(definition.parameters, dict)
        else {}
    )
    required = (
        set(definition.parameters.get("required", []))
        if isinstance(definition.parameters, dict)
        else set()
    )

    param_table = Table(
        title="Parameters Schema", show_header=True, header_style=f"bold {th.primary}"
    )
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

    console.print(
        Panel(
            meta_text,
            border_style=th.border,
            title=f"[bold {th.secondary}]Tool Details: {definition.name}[/bold {th.secondary}]",
        )
    )
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


def render_connectors_catalog(console: Console) -> None:
    """Render the essential tool integrations catalog (Meta Muse / Manus style)."""
    from icarus_core.mcp.config import McpConfigManager
    from icarus_core.tools.catalog import ESSENTIAL_CATALOG

    mgr = McpConfigManager()
    configured_servers = set(mgr.get_servers().keys())
    th = get_theme()

    table = Table(
        title="Essential Tool Connectors Catalog",
        show_header=True,
        header_style=f"bold {th.primary}",
    )
    table.add_column("Connector ID", style=f"bold {th.secondary}", width=16)
    table.add_column("Name", style="bold white", width=28)
    table.add_column("Category", width=18)
    table.add_column("Status", width=16)
    table.add_column("Description")

    for conn in ESSENTIAL_CATALOG:
        if conn.is_built_in:
            status = "[bold green]● Built-in[/bold green]"
        elif conn.id in configured_servers:
            status = "[bold cyan]● Connected[/bold cyan]"
        else:
            status = "[dim]○ Available[/dim]"

        table.add_row(conn.id, conn.name, conn.category, status, conn.description)

    console.print(table)
    console.print(
        f"\n[dim]* To connect an essential tool: [bold {th.primary}]/connect <id>[/bold {th.primary}] or [bold {th.primary}]icarus connect <id>[/bold {th.primary}][/dim]"
    )
    console.print(
        f"[dim]* Example: [bold {th.primary}]icarus connect browser[/bold {th.primary}] or [bold {th.primary}]icarus connect stripe[/bold {th.primary}][/dim]\n"
    )


def connect_tool_interactive(console: Console, connector_id: str | None = None) -> bool:
    """Walk through connecting an essential tool connector from catalog with auto-browser launch."""
    import os
    import webbrowser

    from icarus_core.mcp.config import McpConfigManager, McpServerConfig
    from icarus_core.tools.auth import ToolAuthManager
    from icarus_core.tools.catalog import get_connector

    mgr = McpConfigManager()
    th = get_theme()

    if not connector_id:
        render_connectors_catalog(console)
        try:
            val = console.input(
                f"[bold {th.primary}]Enter Connector ID to connect (or press Enter to cancel): [/bold {th.primary}]"
            ).strip()
            if not val:
                return False
            connector_id = val
        except (KeyboardInterrupt, EOFError):
            return False

    conn = get_connector(connector_id)
    if not conn:
        console.print(f"[bold red]Error:[/bold red] Unknown connector ID '{connector_id}'.")
        console.print("[dim]Run `icarus tools catalog` to view supported connectors.[/dim]")
        return False

    # Fully zero-config built-ins without credentials
    if conn.is_built_in and not conn.env_vars:
        console.print(
            f"[bold green]✔ '{conn.name}' is already built-in and active out-of-the-box![/bold green]"
        )
        return True

    console.print(f"\n[bold {th.primary}]Connecting {conn.name}...[/bold {th.primary}]")
    console.print(f"[dim]{conn.description}[/dim]")

    # Auto-launch default browser for OAuth / developer keys
    if conn.doc_url:
        console.print(
            "\n[bold cyan]🌐 Opening authorization page in your default browser...[/bold cyan]"
        )
        console.print(f"   👉 [bold underline blue]{conn.doc_url}[/bold underline blue]\n")
        with contextlib.suppress(Exception):
            webbrowser.open(conn.doc_url)

    # Special handling for Gmail
    if conn.id == "gmail":
        console.print("[bold white]Google Account Security -> App Passwords:[/bold white]")
        console.print("[dim]1. Enter app name 'Icarus' and click Create.[/dim]")
        console.print("[dim]2. Copy the 16-character password (e.g., 'abcd efgh ijkl mnop').[/dim]")
        console.print(
            "[dim]Tip: For 1-click OAuth without app passwords, connect Composio: `icarus connect composio`[/dim]\n"
        )

        try:
            email_addr = console.input(
                "[bold yellow]Enter your Gmail address (e.g. you@gmail.com): [/bold yellow]"
            ).strip()
            pwd = console.input(
                "[bold yellow]Enter your 16-char App Password: [/bold yellow]", password=True
            ).strip()
            if not pwd:
                console.print("\n[dim]Connection cancelled.[/dim]")
                return False

            combined = f"{email_addr}:{pwd}" if email_addr else pwd
            ToolAuthManager.save_token("gmail", combined)
            os.environ["GMAIL_APP_PASSWORD"] = combined
            console.print(
                f"[bold green]✔ Successfully connected Gmail ({email_addr or 'default'})![/bold green]"
            )
            console.print(
                "[dim]Tools `gmail_search` and `gmail_send` are now ready for your commands.[/dim]\n"
            )
            return True
        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]Connection cancelled.[/dim]")
            return False

    # Special handling for Google Calendar
    if conn.id == "calendar":
        console.print("[bold white]Google Calendar Credentials:[/bold white]")
        console.print(
            "[dim]Use your Google App Password or Calendar API token to authorize events & scheduling.[/dim]\n"
        )
        try:
            pwd = console.input(
                "[bold yellow]Enter Google App Password or Token: [/bold yellow]", password=True
            ).strip()
            if not pwd:
                console.print("\n[dim]Connection cancelled.[/dim]")
                return False
            ToolAuthManager.save_token("calendar", pwd)
            os.environ["GOOGLE_CALENDAR_TOKEN"] = pwd
            console.print("[bold green]✔ Successfully connected Google Calendar![/bold green]")
            console.print(
                "[dim]Tools `calendar_events` and `calendar_create_event` are now ready.[/dim]\n"
            )
            return True
        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]Connection cancelled.[/dim]")
            return False

    # Zero-secret MCP servers (e.g., Puppeteer browser automation)
    if not conn.env_vars:
        server_cfg = McpServerConfig(
            command=conn.command,
            args=conn.args,
            transport="stdio",
        )
        try:
            mgr.add_server(conn.id, server_cfg)
            console.print(
                f"[bold green]✔ Successfully connected '{conn.name}' (Zero keys required)![/bold green]"
            )
            console.print(
                f"[dim]Tools from '{conn.id}' are now active. Run `/tools` or `icarus tools list` to inspect.[/dim]\n"
            )
            return True
        except Exception as exc:
            console.print(f"[bold red]Failed to save connector:[/bold red] {exc}")
            return False

    # Collect required secrets
    env_dict: dict[str, str] = {}
    for ev in conn.env_vars:
        existing = os.environ.get(ev) or ToolAuthManager.get_token(conn.id)
        prompt_label = f"Enter secret for [bold yellow]{ev}[/bold yellow]"
        if existing:
            prompt_label += " [dim](press Enter to keep existing)[/dim]"
        prompt_label += ": "

        try:
            val = console.input(prompt_label, password=True).strip()
            if val:
                env_dict[ev] = val
                ToolAuthManager.save_token(conn.id, val)
            elif existing:
                env_dict[ev] = existing
            else:
                console.print(
                    f"[yellow]Warning: {ev} was left empty. Tool may fail if required.[/yellow]"
                )
        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]Connection cancelled.[/dim]")
            return False

    server_cfg = McpServerConfig(
        command=conn.command,
        args=conn.args,
        env=env_dict,
        transport="stdio",
    )

    try:
        mgr.add_server(conn.id, server_cfg)
        console.print(f"[bold green]✔ Successfully connected '{conn.name}'![/bold green]")
        console.print(
            f"[dim]Tools from '{conn.id}' are now active. Run `/tools` or `icarus tools list` to inspect.[/dim]\n"
        )
        return True
    except Exception as exc:
        console.print(f"[bold red]Failed to save connector:[/bold red] {exc}")
        return False


@tools_app.command(name="catalog")
def catalog_tools() -> None:
    """Browse the essential tools & connectors catalog (Meta Muse / Manus style)."""
    render_connectors_catalog(console)


@tools_app.command(name="connect")
def connect_tool(
    connector_id: Annotated[
        str | None, typer.Argument(help="Optional Connector ID (e.g. browser, github, stripe).")
    ] = None,
) -> None:
    """Connect and authenticate an essential tool connector."""
    connect_tool_interactive(console, connector_id=connector_id)
