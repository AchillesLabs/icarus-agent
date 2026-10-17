"""Interactive model table rendering and selection UI."""

import sys
from typing import Any

from icarus_contracts import DiscoveredModel
from rich.console import Console
from rich.table import Table

console = Console()


def render_models_table(
    models: list[DiscoveredModel],
    current_model: str | None = None,
    provider: str = "",
) -> None:
    """Render a Rich table displaying available models divided into Free and Paid tiers."""
    if not models:
        console.print(f"[yellow]No models found for provider '{provider}'.[/yellow]")
        return

    table_title = f"{provider.capitalize()} Models Catalog" if provider else "Available Models"
    if current_model:
        table_title += f" [dim](Active: {current_model})[/dim]"

    table = Table(
        title=f"[bold cyan]{table_title}[/bold cyan]",
        show_header=True,
        header_style="bold magenta",
        expand=True,
    )
    table.add_column("#", style="bold cyan", width=5, justify="center")
    table.add_column("Model ID", style="bold white", min_width=24)
    table.add_column("Display Name", style="dim", min_width=18)
    table.add_column("Context", justify="right", width=12)
    table.add_column("Tier", justify="center", width=16)
    table.add_column("Pricing / Details", min_width=26)
    table.add_column("Status", justify="center", width=10)

    free_models = [m for m in models if m.is_free]
    paid_models = [m for m in models if not m.is_free]

    def add_model_row(idx: int, m: DiscoveredModel) -> None:
        ctx_val = m.context_window
        ctx_str = f"{ctx_val // 1000}k" if ctx_val >= 1000 else str(ctx_val)
        tier_str = (
            "[bold green]FREE[/bold green]"
            if m.is_free
            else "[bold yellow]PAID / STD[/bold yellow]"
        )
        status_str = (
            "[bold green]* ACTIVE[/bold green]" if current_model and m.id == current_model else ""
        )
        table.add_row(
            str(idx),
            m.id,
            m.name,
            ctx_str,
            tier_str,
            m.pricing_info,
            status_str,
        )

    idx = 1
    if free_models:
        table.add_section()
        for m in free_models:
            add_model_row(idx, m)
            idx += 1

    if paid_models:
        table.add_section()
        for m in paid_models:
            add_model_row(idx, m)
            idx += 1

    console.print(table)


def select_model_interactive(
    models: list[DiscoveredModel],
    current_model: str | None = None,
    default_index: int = 1,
) -> str:
    """Prompt the user to select a model via arrow-key menu or number prompt."""
    if not models:
        return current_model or ""

    # Try interactive arrow selector via questionary if running in interactive terminal
    if sys.stdin.isatty():
        try:
            import questionary
            from questionary import Choice, Separator

            choices: list[Any] = []
            free_models = [m for m in models if m.is_free]
            paid_models = [m for m in models if not m.is_free]

            def make_title(num: int, m: DiscoveredModel) -> str:
                tag = "[FREE]" if m.is_free else "[PAID]"
                ctx = f"{m.context_window // 1000}k"
                active = " (ACTIVE)" if current_model and m.id == current_model else ""
                return f"{num:2d}) {tag:<6} {m.id} ({m.name}, {ctx}){active}"

            idx = 1
            default_choice_idx = 0

            if free_models:
                choices.append(Separator("── Free Inference Models ──"))
                for m in free_models:
                    if current_model and m.id == current_model:
                        default_choice_idx = len(choices)
                    choices.append(Choice(title=make_title(idx, m), value=m.id))
                    idx += 1

            if paid_models:
                choices.append(Separator("── Paid / Standard Models ──"))
                for m in paid_models:
                    if current_model and m.id == current_model:
                        default_choice_idx = len(choices)
                    choices.append(Choice(title=make_title(idx, m), value=m.id))
                    idx += 1

            selected = questionary.select(
                "Use ↑/↓ arrow keys to select a model (Enter to confirm):",
                choices=choices,
                default=choices[default_choice_idx] if choices else None,
            ).ask()

            if selected:
                return str(selected)
        except Exception:
            pass

    # Fallback to standard numbered prompt
    import typer

    prompt_msg = f"Select model number [1-{len(models)}] or enter Model ID"
    raw_choice = typer.prompt(prompt_msg, default=str(default_index)).strip()

    # Check if user typed a number
    if raw_choice.isdigit():
        choice_num = int(raw_choice)
        if 1 <= choice_num <= len(models):
            return models[choice_num - 1].id

    # Check if user entered an exact model ID
    for m in models:
        if raw_choice.lower() == m.id.lower():
            return m.id

    return models[default_index - 1].id if models else raw_choice


def resolve_model_by_input(
    models: list[DiscoveredModel],
    number: int | None = None,
    model_id: str | None = None,
) -> str | None:
    """Resolve model by 1-based number flag or explicit model ID."""
    if number is not None:
        if 1 <= number <= len(models):
            return models[number - 1].id
        raise ValueError(f"Invalid model number {number}. Must be between 1 and {len(models)}.")

    if model_id is not None and model_id.strip():
        cleaned = model_id.strip()
        # Direct match or return as-is
        for m in models:
            if m.id.lower() == cleaned.lower():
                return m.id
        return cleaned

    return None
