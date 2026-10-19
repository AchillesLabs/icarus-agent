"""Workspace security verification and trusted directories management."""

from __future__ import annotations

import contextlib
import json
import os
import sys
from pathlib import Path

from icarus_core.paths import get_icarus_home
from rich.console import Console


def get_trusted_workspaces_file() -> Path:
    """Return path to trusted workspaces registry file."""
    return get_icarus_home() / "trusted_workspaces.json"


def load_trusted_workspaces() -> set[str]:
    """Load previously trusted workspace directory paths."""
    file_path = get_trusted_workspaces_file()
    if not file_path.exists():
        return set()
    try:
        data = json.loads(file_path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return set(data)
    except Exception:
        pass
    return set()


def add_trusted_workspace(path: Path | str) -> None:
    """Register workspace directory path as trusted."""
    resolved = str(Path(path).resolve())
    trusted = load_trusted_workspaces()
    trusted.add(resolved)
    file_path = get_trusted_workspaces_file()
    file_path.parent.mkdir(parents=True, exist_ok=True)
    with contextlib.suppress(Exception):
        file_path.write_text(json.dumps(sorted(trusted), indent=2), encoding="utf-8")


def is_workspace_trusted(path: Path | str) -> bool:
    """Check if workspace directory is already verified and trusted."""
    resolved = str(Path(path).resolve())
    return resolved in load_trusted_workspaces()


def verify_workspace_trust(
    workspace_path: Path | None = None,
    console: Console | None = None,
    auto_approve: bool = False,
) -> bool:
    """Prompt user for security confirmation if accessing an untrusted directory.

    Returns True if approved to proceed, False if user chooses to exit.
    """
    console = console or Console()
    cwd = (workspace_path or Path.cwd()).resolve()

    # 1. Skip check if explicitly trusted via env or auto_approve flag
    if auto_approve or os.environ.get("ICARUS_TRUST_ALL") == "1":
        return True

    # 2. Skip check if already verified in persistent registry
    if is_workspace_trusted(cwd):
        return True

    # 3. In non-interactive environments (CI, pipes), default to trusted
    if not sys.stdin.isatty():
        return True

    # 4. Display security confirmation dialog
    console.print()
    console.print(
        f"[bold yellow]Accessing workspace:[/bold yellow]\n[bold white]{cwd}[/bold white]\n"
    )
    console.print(
        "[dim]Quick safety check: Is this a project you created or one you trust? "
        "(Like your own code, a well-known open source project, or work from your team). "
        "If not, take a moment to review what's in this folder first.[/dim]\n"
    )
    console.print(
        "[dim]Icarus will be able to read, edit, and execute files and tools here.[/dim]\n"
    )

    try:
        import questionary

        choice = questionary.select(
            "",
            choices=[
                "1. Yes, I trust this folder",
                "2. No, exit",
            ],
            default="1. Yes, I trust this folder",
        ).ask()
    except Exception:
        # Fallback to simple console input if questionary cannot initialize
        console.print("[bold cyan]1.[/bold cyan] Yes, I trust this folder")
        console.print("[bold red]2.[/bold red] No, exit")
        try:
            val = console.input("\nEnter choice [1]: ").strip()
            choice = "2. No, exit" if val == "2" else "1. Yes, I trust this folder"
        except (KeyboardInterrupt, EOFError):
            choice = None

    if choice and "Yes" in choice:
        add_trusted_workspace(cwd)
        console.print("[bold green]✓ Workspace trusted.[/bold green]\n")
        return True

    console.print("[dim]Exiting workspace. Goodbye![/dim]\n")
    return False
