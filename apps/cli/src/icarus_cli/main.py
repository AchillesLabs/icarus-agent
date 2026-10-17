"""Entrypoint for the Icarus CLI application."""

from typing import Annotated

import typer
from icarus_contracts.doctor import HealthStatus
from icarus_core.config import ConfigManager
from icarus_core.credentials import CredentialResolver
from icarus_core.doctor import run_doctor_checks
from icarus_core.paths import get_icarus_log_file
from icarus_core.persistence.migrations.runner import MigrationRunner
from icarus_core.providers import fetch_provider_models
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from icarus_cli import __version__
from icarus_cli.chat import run_chat
from icarus_cli.models_view import (
    render_models_table,
    resolve_model_by_input,
    select_model_interactive,
)
from icarus_cli.run import execute_run

app = typer.Typer(
    name="icarus",
    help="[bold cyan]Icarus[/bold cyan] - Modular, open-source, CLI-first AI agent platform.",
    rich_markup_mode="rich",
    no_args_is_help=True,
)
config_app = typer.Typer(
    name="config",
    help="Inspect and modify Icarus configuration settings.",
    no_args_is_help=True,
)
app.add_typer(config_app, name="config")

console = Console()


def ensure_database_migrated() -> None:
    """Ensure ~/.icarus/ storage is initialized and pending migrations run automatically."""
    try:
        runner = MigrationRunner()
        if not runner.is_migration_up_to_date():
            runner.run_migrations()
    except Exception:
        # Fall through so doctor and commands can report specific diagnostic failures
        pass


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
    ensure_database_migrated()


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


@app.command(name="init")
def init_cmd(
    provider: Annotated[
        str,
        typer.Option("--provider", "-p", help="Primary model provider (groq, openrouter, grok)."),
    ] = "groq",
    model: Annotated[
        str | None,
        typer.Option("--model", "-m", help="Selected model ID for the provider."),
    ] = None,
    number: Annotated[
        int | None,
        typer.Option("--number", "-n", help="Model number from discovered list to select."),
    ] = None,
    api_key: Annotated[
        str | None,
        typer.Option("--api-key", "-k", help="API key for the selected provider."),
    ] = None,
    non_interactive: Annotated[
        bool,
        typer.Option("--non-interactive", help="Run without interactive prompts."),
    ] = False,
) -> None:
    """Initialize Icarus local storage, database, and model credentials."""
    banner = (
        "[bold cyan]Icarus Initialization[/bold cyan]\n"
        "Configuring local environment, database migrations, and secure credentials."
    )
    console.print(Panel(banner, border_style="cyan"))

    ensure_database_migrated()

    selected_provider = provider.lower().strip()
    selected_key = api_key

    if not non_interactive:
        selected_provider = (
            typer.prompt(
                "Select default model provider [groq/openrouter/grok]",
                default=selected_provider,
            )
            .lower()
            .strip()
        )

        if not selected_key:
            selected_key = typer.prompt(
                f"Enter API key for {selected_provider}",
                hide_input=True,
            )

    resolver = CredentialResolver()
    if selected_key and len(selected_key.strip()) > 0:
        resolver.store(selected_provider, selected_key.strip())
        console.print(
            f"[bold green]Securely stored API key for '{selected_provider}' "
            f"in the OS keyring.[/bold green]"
        )

    cfg_manager = ConfigManager()
    cfg = cfg_manager.load_config()
    cfg.default_provider = selected_provider

    # Discover models dynamically on the provided key
    effective_key = selected_key or resolver.resolve(selected_provider).secret
    discovered = []
    try:
        with console.status(f"[cyan]Fetching available models for '{selected_provider}'...[/cyan]"):
            discovered = fetch_provider_models(selected_provider, api_key=effective_key)
    except Exception:
        discovered = []

    chosen_model = model
    if chosen_model is None and number is not None:
        try:
            chosen_model = resolve_model_by_input(discovered, number=number)
        except ValueError as err:
            console.print(f"[bold red]Selection Error:[/bold red] {err}")
            raise typer.Exit(code=1) from None

    if chosen_model is None:
        if discovered:
            if not non_interactive:
                render_models_table(discovered, current_model=cfg.model, provider=selected_provider)
                chosen_model = select_model_interactive(discovered, current_model=cfg.model)
            else:
                if selected_provider == "openrouter":
                    chosen_model = "anthropic/claude-3.5-sonnet"
                elif selected_provider == "groq":
                    chosen_model = "openai/gpt-oss-120b"
                else:
                    chosen_model = discovered[0].id
        else:
            if selected_provider == "openrouter":
                chosen_model = "anthropic/claude-3.5-sonnet"
            elif selected_provider == "groq":
                chosen_model = "openai/gpt-oss-120b"
            else:
                chosen_model = "grok-2"

    cfg.model = chosen_model
    cfg_manager.save_config(cfg)

    console.print(
        f"[bold green]Configuration saved to {cfg_manager.config_path.as_posix()}[/bold green]"
    )
    console.print(
        f"[bold cyan]Active model set to:[/bold cyan] [bold yellow]{cfg.model}[/bold yellow] "
        f"([dim]{selected_provider}[/dim])"
    )
    console.print(
        "\n[bold cyan]Icarus initialization complete! "
        "Run `icarus doctor` or `icarus chat` to start.[/bold cyan]\n"
    )


@app.command(name="models")
def models_cmd(
    provider: Annotated[
        str | None,
        typer.Option("--provider", "-p", help="Provider to inspect (groq, openrouter, grok)."),
    ] = None,
    set_model: Annotated[
        str | None,
        typer.Option("--set", "-s", help="Model ID to activate and save in config."),
    ] = None,
    number: Annotated[
        int | None,
        typer.Option("--number", "-n", help="Model number from the list to activate."),
    ] = None,
    non_interactive: Annotated[
        bool,
        typer.Option("--non-interactive", help="Display models without interactive prompt."),
    ] = False,
) -> None:
    """List all models available on the provider (Free vs Paid tiers) and switch active model."""
    cfg_manager = ConfigManager()
    cfg = cfg_manager.load_config()
    target_provider = (provider or cfg.default_provider).lower().strip()

    resolver = CredentialResolver()
    cred = resolver.resolve(target_provider)

    with console.status(f"[cyan]Fetching models for '{target_provider}'...[/cyan]"):
        models = fetch_provider_models(target_provider, api_key=cred.secret)

    if not models:
        console.print(
            f"[yellow]No models found or unable to fetch models for '{target_provider}'.[/yellow]"
        )
        if not cred.is_available:
            console.print(
                f"[dim]No API key found for '{target_provider}'. "
                f"Run `icarus init -p {target_provider}` first.[/dim]"
            )
        raise typer.Exit(code=1)

    chosen_model: str | None = None
    if number is not None:
        try:
            chosen_model = resolve_model_by_input(models, number=number)
        except ValueError as err:
            console.print(f"[bold red]Selection Error:[/bold red] {err}")
            raise typer.Exit(code=1) from None
    elif set_model is not None:
        chosen_model = resolve_model_by_input(models, model_id=set_model)

    if chosen_model is not None:
        cfg.model = chosen_model
        cfg.default_provider = target_provider
        cfg_manager.save_config(cfg)
        console.print(
            f"[bold green]Active model switched to '{chosen_model}' "
            f"for provider '{target_provider}'.[/bold green]"
        )
        return

    render_models_table(models, current_model=cfg.model, provider=target_provider)

    if not non_interactive:
        selected = select_model_interactive(models, current_model=cfg.model)
        if selected and selected != cfg.model:
            cfg.model = selected
            cfg.default_provider = target_provider
            cfg_manager.save_config(cfg)
            console.print(
                f"\n[bold green]Successfully switched active model to '{selected}'![/bold green]\n"
            )
        elif selected == cfg.model:
            console.print(f"\n[dim]Model '{selected}' remains active.[/dim]\n")


@app.command(name="chat")
def chat_cmd(
    resume: Annotated[
        bool,
        typer.Option("--resume", "-r", help="Resume the most recent conversation session."),
    ] = False,
    session: Annotated[
        str | None,
        typer.Option("--session", "-s", help="Load an existing conversation thread by ID."),
    ] = None,
    provider: Annotated[
        str | None,
        typer.Option("--provider", "-p", help="Override active model provider (grok, mock, etc.)."),
    ] = None,
    model: Annotated[
        str | None,
        typer.Option("--model", "-m", help="Override active model name."),
    ] = None,
    temperature: Annotated[
        float | None,
        typer.Option("--temperature", "-t", help="Sampling temperature between 0.0 and 2.0."),
    ] = None,
) -> None:
    """Launch an interactive streaming chat REPL session."""
    ensure_database_migrated()
    try:
        run_chat(
            provider_name=provider,
            model_name=model,
            session_id=session,
            resume=resume,
            temperature=temperature,
            console=console,
        )
    except ValueError as exc:
        raise typer.Exit(code=1) from exc


@app.command(name="run")
def run_cmd(
    prompt: Annotated[
        str | None,
        typer.Argument(
            help="Prompt text to execute. If omitted or '-', reads prompt from standard input.",
        ),
    ] = None,
    provider: Annotated[
        str | None,
        typer.Option("--provider", "-p", help="Override active model provider (grok, mock, etc.)."),
    ] = None,
    model: Annotated[
        str | None,
        typer.Option("--model", "-m", help="Override active model name."),
    ] = None,
    temperature: Annotated[
        float | None,
        typer.Option("--temperature", "-t", help="Sampling temperature between 0.0 and 2.0."),
    ] = None,
) -> None:
    """Execute a non-interactive one-shot query and stream tokens to stdout."""
    ensure_database_migrated()
    exit_code = execute_run(
        prompt=prompt,
        provider_name=provider,
        model_name=model,
        temperature=temperature,
        console=console,
    )
    if exit_code != 0:
        raise typer.Exit(code=exit_code)


@app.command(name="logs")
def logs_cmd(
    tail: Annotated[
        int,
        typer.Option("--tail", "-n", help="Number of recent log lines to display."),
    ] = 50,
) -> None:
    """Inspect recent developer log records from ~/.icarus/logs/cli.log."""
    log_file = get_icarus_log_file()
    if not log_file.exists():
        console.print(f"[dim]No logs found at {log_file.as_posix()}[/dim]")
        return

    lines = log_file.read_text(encoding="utf-8", errors="replace").splitlines()
    recent = lines[-tail:] if tail > 0 else lines
    for line in recent:
        console.print(line)


@config_app.command(name="list")
def config_list() -> None:
    """Display active Icarus configuration settings and credential status."""
    cfg_manager = ConfigManager()
    settings = cfg_manager.list_settings()
    active_provider = settings.get("default_provider", "grok")

    resolver = CredentialResolver()
    cred = resolver.resolve(active_provider)

    table = Table(title="Icarus Configuration", show_header=True, header_style="bold cyan")
    table.add_column("Setting", width=25, style="bold")
    table.add_column("Value", style="green")

    for key, value in settings.items():
        table.add_row(key, str(value))

    cred_status = (
        f"[bold green]Configured ({cred.masked}, source: {cred.source.value})[/bold green]"
        if cred.is_available
        else "[bold yellow]Missing (run 'icarus init')[/bold yellow]"
    )
    table.add_row(f"credential ({active_provider})", cred_status)

    console.print(table)


@config_app.command(name="set")
def config_set(
    key: Annotated[str, typer.Argument(help="Configuration setting name to update.")],
    val: Annotated[str, typer.Argument(help="New value for the setting.")],
) -> None:
    """Update a configuration setting in ~/.icarus/config.toml."""
    cfg_manager = ConfigManager()
    try:
        updated = cfg_manager.set(key, val)
        new_val = getattr(updated, key)
        console.print(
            f"[bold green]Updated[/bold green] [cyan]{key}[/cyan] = [yellow]{new_val}[/yellow]"
        )
    except KeyError as exc:
        console.print(f"[bold red]Configuration error:[/bold red] {exc}")
        raise typer.Exit(code=1) from exc
    except ValueError as exc:
        console.print(f"[bold red]Validation error:[/bold red] {exc}")
        raise typer.Exit(code=1) from exc


if __name__ == "__main__":
    app()
