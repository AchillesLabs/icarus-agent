"""Entrypoint for the Icarus CLI application."""

from typing import Annotated

import typer
from icarus_contracts.doctor import HealthStatus
from icarus_core.doctor import run_doctor_checks
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from icarus_cli import __version__

app = typer.Typer(
    name="icarus",
    help="[bold cyan]Icarus[/bold cyan] - Modular, open-source, CLI-first AI agent platform.",
    rich_markup_mode="rich",
    no_args_is_help=True,
)
console = Console()


def version_callback(value: bool) -> None:
    """Print the version and exit."""
    if value:
        console.print(
            f"[bold cyan]icarus[/bold cyan] version [bold green]{__version__}[/bold green]"
        )
        raise typer.Exit()


@app.callback()
def main(
    version: Annotated[
        bool | None,
        typer.Option(
            "--version",
            "-v",
            help="Show the version and exit.",
            callback=version_callback,
            is_eager=True,
        ),
    ] = None,
) -> None:
    """Icarus root CLI command callback."""


@app.command(name="doctor")
def doctor() -> None:
    """Run environment and workspace health diagnostics."""
    banner_text = (
        "[bold cyan]Icarus Doctor[/bold cyan]\n"
        "Validating interpreter, workspace integrity, and storage readiness..."
    )
    console.print(Panel(banner_text, border_style="cyan"))

    report = run_doctor_checks()

    table = Table(title="Diagnostic Checks", show_header=True, header_style="bold magenta")
    table.add_column("Status", width=10, justify="center")
    table.add_column("Check Name", width=28)
    table.add_column("Message", style="dim")
    table.add_column("Details / Action", style="italic")

    status_badges = {
        HealthStatus.OK: "[bold green]PASS[/bold green]",
        HealthStatus.WARNING: "[bold yellow]WARN[/bold yellow]",
        HealthStatus.FAIL: "[bold red]FAIL[/bold red]",
    }

    for check in report.checks:
        badge = status_badges.get(check.status, str(check.status))
        details_or_fix = check.fix_hint or check.details or ""
        table.add_row(badge, check.name, check.message, details_or_fix)

    console.print(table)

    if report.is_healthy:
        console.print("\n[bold green][OK] Environment is healthy and ready.[/bold green]\n")
        raise typer.Exit(code=0)
    else:
        failure_msg = (
            "\n[bold red][FAIL] Diagnostic checks encountered failures. "
            "Please resolve the items above.[/bold red]\n"
        )
        console.print(failure_msg)
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
