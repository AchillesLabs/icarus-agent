"""CLI commands for managing, discovering, and authoring agent skills."""

from pathlib import Path
from typing import Annotated

import typer
from icarus_core.skills import create_skill, discover_skills, pull_skill
from rich.console import Console
from rich.table import Table

skills_app = typer.Typer(
    name="skills",
    help="Manage, discover, pull, and scaffold agent skills.",
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
        "[dim]* To pull an external skill, run: [bold #C084FC]icarus skills pull <url_or_repo>[/bold #C084FC][/dim]\n"
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


def _execute_pull(
    source: str,
    name: str | None,
    skill: str | None,
    global_scope: bool,
    overwrite: bool,
) -> None:
    with console.status(f"[bold #C084FC]Pulling external skill from '{source}'...[/bold #C084FC]"):
        try:
            installed = pull_skill(
                source=source,
                workspace_dir=Path.cwd(),
                global_scope=global_scope,
                skill_name=name or skill,
                overwrite=overwrite,
            )
        except Exception as exc:
            console.print(f"[bold red]Error pulling skill:[/bold red] {exc}")
            raise typer.Exit(code=1) from exc

    scope_label = "global (~/.icarus/skills/)" if global_scope else "workspace (.agents/skills/)"
    console.print(
        f"\n[bold green]✔ Successfully installed {len(installed)} skill(s)[/bold green] into {scope_label}:"
    )
    for sk in installed:
        console.print(
            f"  • [bold #E9D5FF]{sk.name}[/bold #E9D5FF] - {sk.description}\n    [dim]({sk.path})[/dim]"
        )
    console.print()


@skills_app.command(name="pull")
def pull_skill_cmd(
    source: Annotated[
        str,
        typer.Argument(
            help="Source to pull from (URL to SKILL.md, Git repository, GitHub owner/repo, or local path)."
        ),
    ],
    name: Annotated[
        str | None,
        typer.Option("--name", "-n", help="Override installed skill name."),
    ] = None,
    skill: Annotated[
        str | None,
        typer.Option(
            "--skill", "-s", help="Specific skill name to extract from multi-skill repository."
        ),
    ] = None,
    global_scope: Annotated[
        bool,
        typer.Option(
            "--global", "-g", help="Install globally in ~/.icarus/skills/ instead of workspace."
        ),
    ] = False,
    overwrite: Annotated[
        bool,
        typer.Option(
            "--overwrite", "-f", help="Overwrite existing skill if it already exists."
        ),
    ] = False,
) -> None:
    """Pull and install an external skill from a URL, Git repository, GitHub shorthand, or local path."""
    _execute_pull(source, name, skill, global_scope, overwrite)


@skills_app.command(name="install")
def install_skill_cmd(
    source: Annotated[
        str,
        typer.Argument(
            help="Source to install from (URL to SKILL.md, Git repository, GitHub owner/repo, or local path)."
        ),
    ],
    name: Annotated[
        str | None,
        typer.Option("--name", "-n", help="Override installed skill name."),
    ] = None,
    skill: Annotated[
        str | None,
        typer.Option(
            "--skill", "-s", help="Specific skill name to extract from multi-skill repository."
        ),
    ] = None,
    global_scope: Annotated[
        bool,
        typer.Option(
            "--global", "-g", help="Install globally in ~/.icarus/skills/ instead of workspace."
        ),
    ] = False,
    overwrite: Annotated[
        bool,
        typer.Option(
            "--overwrite", "-f", help="Overwrite existing skill if it already exists."
        ),
    ] = False,
) -> None:
    """Install an external skill (alias for 'pull')."""
    _execute_pull(source, name, skill, global_scope, overwrite)


@skills_app.command(name="add")
def add_skill_cmd(
    source: Annotated[
        str,
        typer.Argument(
            help="Source to add from (URL to SKILL.md, Git repository, GitHub owner/repo, or local path)."
        ),
    ],
    name: Annotated[
        str | None,
        typer.Option("--name", "-n", help="Override installed skill name."),
    ] = None,
    skill: Annotated[
        str | None,
        typer.Option(
            "--skill", "-s", help="Specific skill name to extract from multi-skill repository."
        ),
    ] = None,
    global_scope: Annotated[
        bool,
        typer.Option(
            "--global", "-g", help="Install globally in ~/.icarus/skills/ instead of workspace."
        ),
    ] = False,
    overwrite: Annotated[
        bool,
        typer.Option(
            "--overwrite", "-f", help="Overwrite existing skill if it already exists."
        ),
    ] = False,
) -> None:
    """Add an external skill (alias for 'pull')."""
    _execute_pull(source, name, skill, global_scope, overwrite)

