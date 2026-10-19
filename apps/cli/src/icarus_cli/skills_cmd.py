"""CLI commands for managing, discovering, and authoring agent skills."""

from pathlib import Path
from typing import Annotated

import typer
from icarus_core.skills import create_skill, discover_skills
from rich.console import Console
from rich.table import Table

skills_app = typer.Typer(
    name="skills",
    help="Manage, discover, and scaffold agent skills.",
    rich_markup_mode="rich",
    no_args_is_help=False,
)

console = Console()


@skills_app.callback(invoke_without_command=True)
def list_skills(
    ctx: typer.Context,
) -> None:
    """List all available workspace and global skills."""
    if ctx.invoked_subcommand is not None:
        return

    skills = discover_skills(Path.cwd())
    table = Table(
        title="Discovered Icarus Skills",
        show_header=True,
        header_style="bold #C084FC",
    )
    table.add_column("Skill Name", style="bold #E9D5FF", width=24)
    table.add_column("Scope", style="dim", width=12)
    table.add_column("Path / Description")

    if not skills:
        table.add_row(
            "No skills loaded",
            "-",
            "Add a folder with SKILL.md to .agents/skills/ or ~/.icarus/skills/",
        )
    else:
        for sk in skills:
            table.add_row(sk.name, sk.scope, f"{sk.description}\n[dim]({sk.path})[/dim]")

    console.print()
    console.print(table)
    console.print(
        "[dim]* To create a new skill, run: [bold #C084FC]icarus skills new <name> --desc '<description>'[/bold #C084FC][/dim]\n"
    )


@skills_app.command(name="new")
def new_skill(
    name: Annotated[
        str,
        typer.Argument(help="Name of the skill to create (e.g. flight-finder)."),
    ],
    desc: Annotated[
        str,
        typer.Option("--desc", "-d", help="Brief description of when and how to use the skill."),
    ] = "",
    global_scope: Annotated[
        bool,
        typer.Option(
            "--global", "-g", help="Create globally in ~/.icarus/skills/ instead of workspace."
        ),
    ] = False,
) -> None:
    """Scaffold a new skill directory with a starter SKILL.md template."""
    try:
        skill_file = create_skill(
            name=name,
            description=desc,
            workspace_dir=Path.cwd(),
            global_scope=global_scope,
        )
        scope_label = (
            "global (~/.icarus/skills/)" if global_scope else "workspace (.agents/skills/)"
        )
        console.print(
            f"[bold green]✔ Successfully created skill '{name}'[/bold green] in {scope_label}!\n"
            f"[dim]File:[/dim] [bold cyan]{skill_file}[/bold cyan]\n\n"
            "[dim]Edit the SKILL.md file to define custom prompts, rules, and workflows for your agent.[/dim]"
        )
    except Exception as exc:
        console.print(f"[bold red]Error creating skill:[/bold red] {exc}")
        raise typer.Exit(code=1) from exc
