"""CLI command suite for Model Context Protocol (MCP) server configuration."""

from __future__ import annotations

from typing import Annotated

import typer
from icarus_core.mcp.config import McpConfigManager, McpServerConfig
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

mcp_app = typer.Typer(
    name="mcp",
    help="Manage, test, and inspect Model Context Protocol (MCP) servers.",
    rich_markup_mode="rich",
    no_args_is_help=True,
)
console = Console()


@mcp_app.command(
    name="add",
    context_settings={"ignore_unknown_options": True, "allow_extra_args": True},
)
def mcp_add(
    ctx: typer.Context,
    name: Annotated[
        str,
        typer.Argument(help="Unique identifier name for this MCP server."),
    ],
    command: Annotated[
        str | None,
        typer.Argument(
            help="Executable command for stdio transport, or URL for SSE transport.",
        ),
    ] = None,
    args: Annotated[
        list[str] | None,
        typer.Argument(help="Optional command line arguments to pass to the MCP server process."),
    ] = None,
    transport: Annotated[
        str,
        typer.Option("--transport", "-t", help="Transport mechanism: 'stdio' or 'sse'."),
    ] = "stdio",
    sse: Annotated[
        bool,
        typer.Option("--sse", help="Convenience flag setting transport to SSE."),
    ] = False,
    stdio: Annotated[
        bool,
        typer.Option("--stdio", help="Convenience flag setting transport to stdio."),
    ] = False,
    url: Annotated[
        str | None,
        typer.Option("--url", "-u", help="Endpoint URL for SSE transport."),
    ] = None,
    env: Annotated[
        list[str] | None,
        typer.Option("--env", "-e", help="Environment variables in KEY=VALUE format."),
    ] = None,
    header: Annotated[
        list[str] | None,
        typer.Option("--header", "-H", help="HTTP headers for SSE transport in Key=Value format."),
    ] = None,
    cwd: Annotated[
        str | None,
        typer.Option("--cwd", help="Working directory for stdio subprocess."),
    ] = None,
    timeout: Annotated[
        float,
        typer.Option("--timeout", help="Default timeout in seconds for operations."),
    ] = 30.0,
) -> None:
    """Register and persist a new MCP server configuration in ~/.icarus/mcp.json."""
    effective_transport = "sse" if sse else ("stdio" if stdio else transport.lower().strip())
    if effective_transport not in ("stdio", "sse"):
        console.print(f"[bold red]Error:[/bold red] Unsupported transport '{effective_transport}'. Must be 'stdio' or 'sse'.")
        raise typer.Exit(code=1)

    parsed_env: dict[str, str] = {}
    if env:
        for item in env:
            k, sep, v = item.partition("=")
            if sep:
                parsed_env[k.strip()] = v.strip()

    parsed_headers: dict[str, str] = {}
    if header:
        for item in header:
            k, sep, v = item.partition("=")
            if sep:
                parsed_headers[k.strip()] = v.strip()

    effective_cmd: str | None = None
    effective_url: str | None = None

    if effective_transport == "sse":
        effective_url = url or command
        if not effective_url:
            console.print("[bold red]Error:[/bold red] SSE transport requires a valid endpoint URL.")
            raise typer.Exit(code=1)
    else:
        effective_cmd = command
        if not effective_cmd:
            console.print("[bold red]Error:[/bold red] Stdio transport requires an executable command.")
            raise typer.Exit(code=1)

    combined_args = list(args or []) + list(ctx.args or [])

    config = McpServerConfig(
        transport=effective_transport,
        command=effective_cmd,
        args=combined_args,
        env=parsed_env,
        url=effective_url,
        headers=parsed_headers,
        cwd=cwd,
        timeout=timeout,
    )

    mgr = McpConfigManager()
    mgr.add_server(name, config)

    console.print(f"[bold green]Successfully registered MCP server '[cyan]{name}[/cyan]'![/bold green]")
    if effective_transport == "stdio":
        console.print(f"  [dim]Command:[/dim] {effective_cmd} {' '.join(combined_args)}")
    else:
        console.print(f"  [dim]URL:[/dim] {effective_url}")
    console.print(f"  [dim]Config saved to:[/dim] {mgr.config_path}")
    console.print(f"[dim]Run `icarus mcp test {name}` to verify connection and inspect tools.[/dim]")


@mcp_app.command(name="list")
def mcp_list() -> None:
    """Display all configured MCP servers and their transport settings."""
    mgr = McpConfigManager()
    servers = mgr.get_servers()

    if not servers:
        console.print("[yellow]No MCP servers configured.[/yellow]")
        console.print("[dim]Use `icarus mcp add <name> <command> [args...]` to register an MCP server.[/dim]")
        return

    table = Table(title="Configured MCP Servers", show_header=True, header_style="bold cyan")
    table.add_column("Server Name", style="bold magenta", width=18)
    table.add_column("Transport", style="cyan", width=10)
    table.add_column("Command / Target", style="green")
    table.add_column("Details", style="dim")

    for name, s_cfg in servers.items():
        if s_cfg.transport == "sse":
            target = s_cfg.url or "N/A"
            details = f"Headers: {len(s_cfg.headers)}" if s_cfg.headers else "No custom headers"
        else:
            cmd_str = s_cfg.command or "N/A"
            if s_cfg.args:
                cmd_str += " " + " ".join(s_cfg.args)
            target = cmd_str
            details = f"Env: {len(s_cfg.env)}" if s_cfg.env else "No env vars"

        table.add_row(name, s_cfg.transport.upper(), target, details)

    console.print(table)


@mcp_app.command(name="test")
def mcp_test(
    name: Annotated[
        str,
        typer.Argument(help="Identifier name of the configured MCP server to test."),
    ],
    timeout: Annotated[
        float,
        typer.Option("--timeout", "-t", help="Connection and handshake timeout in seconds."),
    ] = 15.0,
) -> None:
    """Connect to a configured MCP server, perform handshake, and list discovered tools."""
    mgr = McpConfigManager()
    server = mgr.get_server(name)
    if not server:
        console.print(f"[bold red]Error:[/bold red] MCP server '[yellow]{name}[/yellow]' is not configured.")
        console.print("[dim]Run `icarus mcp list` to view configured servers.[/dim]")
        raise typer.Exit(code=1)

    with console.status(f"[cyan]Connecting to MCP server '{name}' and initializing...[/cyan]"):
        try:
            server_info, tools = mgr.test_server_sync(name=name, timeout=timeout)
        except Exception as exc:
            console.print(f"[bold red]Connection failed:[/bold red] {exc}")
            raise typer.Exit(code=1) from None

    s_name = server_info.get("name", name)
    s_ver = server_info.get("version", "unknown")
    console.print(Panel(
        f"[bold green]MCP Handshake Successful![/bold green]\n"
        f"Server: [bold]{s_name}[/bold] (v{s_ver})\n"
        f"Exposed Tools: [bold yellow]{len(tools)}[/bold yellow]",
        title=f"MCP Server: {name}",
        border_style="green",
    ))

    if not tools:
        console.print("[dim]This server declared 0 tools.[/dim]")
        return

    table = Table(title=f"Discovered Tools for '{name}'", show_header=True, header_style="bold magenta")
    table.add_column("Tool Name", style="bold cyan", width=24)
    table.add_column("Description", style="white")
    table.add_column("Parameters", style="dim", width=28)

    for tool in tools:
        props = tool.inputSchema.get("properties", {}) if isinstance(tool.inputSchema, dict) else {}
        reqs = tool.inputSchema.get("required", []) if isinstance(tool.inputSchema, dict) else []
        param_list = [f"{p}*" if p in reqs else p for p in props.keys()]
        param_summary = ", ".join(param_list) if param_list else "None"
        table.add_row(tool.name, tool.description or "", param_summary)

    console.print(table)


@mcp_app.command(name="remove")
def mcp_remove(
    name: Annotated[
        str,
        typer.Argument(help="Identifier name of the MCP server to remove."),
    ],
) -> None:
    """Unregister and remove an MCP server from ~/.icarus/mcp.json."""
    mgr = McpConfigManager()
    removed = mgr.remove_server(name)
    if not removed:
        console.print(f"[bold red]Error:[/bold red] MCP server '[yellow]{name}[/yellow]' is not configured.")
        raise typer.Exit(code=1)

    console.print(f"[bold green]Successfully removed MCP server '[cyan]{name}[/cyan]'.[/bold green]")
