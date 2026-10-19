"""Terminal User Interface (TUI) workspace components for Icarus Agent.

Provides alternate screen buffer transitions (\033[?1049h / \033[?1049l),
pinned status header bars, and prompt_toolkit interactive sessions with
persistent history and keybindings.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, TextIO

from icarus_core.paths import get_icarus_home
from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.history import FileHistory
from prompt_toolkit.key_binding import KeyBindings, KeyPressEvent
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from icarus_cli import __version__

# Standard ANSI escape codes for alternate screen buffer
ESC_ENTER_ALT_SCREEN = "\033[?1049h"
ESC_LEAVE_ALT_SCREEN = "\033[?1049l"
ESC_CLEAR_SCREEN = "\033[2J"
ESC_HOME_CURSOR = "\033[H"
ESC_SHOW_CURSOR = "\033[?25h"
ESC_HIDE_CURSOR = "\033[?25l"


class AlternateScreenBuffer:
    """Manages terminal transitions to and from the alternate screen buffer.

    Enters the alternate screen buffer with screen clear and cursor home,
    and guarantees restoration of the standard terminal buffer and scrollback on exit.
    """

    def __init__(
        self,
        stream: TextIO | None = None,
        force: bool = False,
    ) -> None:
        self.stream = stream or sys.stdout
        self.force = force
        self.is_active = False

    @property
    def should_activate(self) -> bool:
        """Return True if alternate screen buffer should be activated.

        Defaults to False so terminal preserves native scrollback and mouse wheel scrolling,
        matching standard CLI behavior (e.g. Hermes Agent).
        """
        return self.force

    def enter(self) -> None:
        """Switch to alternate screen buffer and home cursor."""
        if not self.should_activate or self.is_active:
            return
        try:
            self.stream.write(
                f"{ESC_ENTER_ALT_SCREEN}{ESC_CLEAR_SCREEN}{ESC_HOME_CURSOR}{ESC_SHOW_CURSOR}"
            )
            self.stream.flush()
            self.is_active = True
        except Exception:
            self.is_active = False

    def exit(self) -> None:
        """Exit alternate screen buffer and restore terminal cursor/history."""
        if not self.is_active:
            return
        try:
            self.stream.write(f"{ESC_LEAVE_ALT_SCREEN}{ESC_SHOW_CURSOR}")
            self.stream.flush()
        except Exception:
            pass
        finally:
            self.is_active = False

    def __enter__(self) -> AlternateScreenBuffer:
        self.enter()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.exit()


ICARUS_BANNER = """[bold #C084FC]█ █▀▀ ▄▀█ █▀█ █░█ █▀▀ ▄▄ ▄▀█ █▀▀ █▀▀ █▄░█ ▀█▀
█ █▄▄ █▀█ █▀▄ █▄█ ▄▄█ ░░ █▀█ █▄█ ██▄ █░▀█ ░█░[/bold #C084FC]"""

ICARUS_SPRITE = """[bold #C084FC]
  ▄▄                     ▄▄
 █▀██▄   ▄▄       ▄▄   ▄██▀█
 ██ ███▄  ▀█▄   ▄█▀  ▄███ ██
 ▀██ ▀███▄ ▀█▄ ▄█▀ ▄███▀ ██▀
  ▀███▄███████████████▄███▀
    ▀███████████████████▀
       ▀█████████████▀
          ▀███████▀
             ▀█▀[/bold #C084FC]"""


def render_workspace_header(
    console: Console,
    model: str,
    provider: str,
    session_id: str,
    tokens_used: int = 0,
    token_budget: int = 128000,
    mode: str = "Autonomous Personal Agent",
    remote_url: str | None = None,
) -> None:
    """Render the Hermes-style top status dashboard with purple accent and dynamic skills."""
    pct = (tokens_used / token_budget * 100) if token_budget > 0 else 0.0

    try:
        cwd = str(Path.cwd().resolve())
    except Exception:
        cwd = "Workspace"

    status_badge = (
        f"[bold cyan]REMOTE ({remote_url})[/bold cyan]"
        if remote_url
        else "[bold #C084FC]LOCAL RUNTIME[/bold #C084FC]"
    )
    tokens_info = (
        f"[bold #E9D5FF]{tokens_used:,}[/bold #E9D5FF] / "
        f"[dim]{token_budget:,}[/dim] [dim]({pct:.1f}%)[/dim]"
    )

    meta_text = (
        f"[bold #E9D5FF]{model}[/bold #E9D5FF] [dim]· {provider}[/dim]\n"
        f"[dim]{cwd}[/dim]\n"
        f"[dim]Session: {session_id}[/dim]"
    )

    from icarus_core.skills import discover_skills

    try:
        discovered_skills = discover_skills(Path(cwd))
    except Exception:
        discovered_skills = []

    if discovered_skills:
        skill_names = [s.name for s in discovered_skills]
        if len(skill_names) <= 3:
            skills_preview = ", ".join(skill_names)
        else:
            skills_preview = f"{', '.join(skill_names[:3])}, +{len(skill_names) - 3} more"
        skills_line = f"{skills_preview} ({len(discovered_skills)} skills)"
    else:
        skills_line = "None loaded (.agents/skills/)"

    right_text = (
        "[bold #C084FC]Available Tools[/bold #C084FC]\n"
        "[dim]file: read, write, search\n"
        "shell: run_command\n"
        "web: web_search, fetch_webpage\n"
        "system: location, reminders (8 tools)[/dim]\n\n"
        "[bold #C084FC]Available Skills[/bold #C084FC]\n"
        f"[dim]{skills_line}[/dim]\n\n"
        "[bold #C084FC]Shortcuts[/bold #C084FC]\n"
        "[bold #C084FC]/help[/bold #C084FC] [dim]Commands[/dim] · "
        "[bold #C084FC]/skills[/bold #C084FC] [dim]Skills[/dim] · "
        "[bold #C084FC]/models[/bold #C084FC] [dim]Switch[/dim]"
    )

    left_table = Table.grid(padding=(0, 0))
    left_table.add_row(ICARUS_SPRITE)
    left_table.add_row(meta_text)

    main_grid = Table.grid(padding=(0, 3))
    main_grid.add_column()
    main_grid.add_column()
    main_grid.add_row(left_table, right_text)

    panel = Panel(
        main_grid,
        border_style="#A855F7",
        title=f"[bold #E9D5FF]─── ICARUS AGENT CHAT v{__version__} ───[/bold #E9D5FF]",
        subtitle=f"[dim]{mode}  •  {status_badge}  •  {tokens_info}[/dim]",
        padding=(0, 1),
    )

    console.print()
    console.print(ICARUS_BANNER)
    console.print()
    console.print(panel)
    console.print(
        "[dim]Welcome to Icarus Agent! Type your message or [bold #C084FC]/help[/bold #C084FC] for commands.[/dim]"
    )
    console.print(
        "[dim]* Tip: Icarus can search live flights, weather, compare prices, edit code, and manage tasks.[/dim]"
    )
    console.print()


def get_history_file() -> Path:
    """Return the path to the persistent CLI chat history file."""
    history_dir = get_icarus_home()
    history_dir.mkdir(parents=True, exist_ok=True)
    return history_dir / "history"


class InteractivePrompt:
    """Wraps prompt_toolkit.PromptSession with persistent history and keybindings.

    Falls back cleanly to console.input or stdin in non-interactive/test environments.
    """

    def __init__(
        self,
        console: Console | None = None,
        stdin: TextIO | None = None,
        history_file: Path | None = None,
    ) -> None:
        self.console = console or Console()
        self.stdin = stdin or sys.stdin
        self.history_path = history_file or get_history_file()
        self._session: PromptSession[str] | None = None

        if self.is_interactive:
            self._init_prompt_toolkit()

    @property
    def is_interactive(self) -> bool:
        """Check if running in an interactive TTY."""
        try:
            return hasattr(self.stdin, "isatty") and self.stdin.isatty()
        except Exception:
            return False

    def _init_prompt_toolkit(self) -> None:
        """Initialize prompt_toolkit PromptSession with custom keybindings."""
        kb = KeyBindings()

        @kb.add("c-c")
        def _on_ctrl_c(event: KeyPressEvent) -> None:
            """Reset the buffer on Ctrl+C; if already empty, raise KeyboardInterrupt."""
            buf = event.current_buffer
            if buf.text:
                buf.reset()
            else:
                event.cli.output.write("\n")
                raise KeyboardInterrupt

        try:
            self._session = PromptSession(
                history=FileHistory(str(self.history_path)),
                key_bindings=kb,
            )
        except Exception:
            self._session = None

    def read_input(self, prompt_text: str = "> ", rprompt_text: str | None = None) -> str:
        """Read a line of user input, supporting interactive prompt_toolkit or fallback."""
        if self._session is not None and self.is_interactive:
            formatted_prompt = HTML(f"<b><ansimagenta>{prompt_text}</ansimagenta></b>")
            rprompt = HTML(f"<ansigray>{rprompt_text}</ansigray>") if rprompt_text else None
            return self._session.prompt(formatted_prompt, rprompt=rprompt)

        # Fallback for non-interactive runners or redirected stdin
        if hasattr(self.console, "input") and self.stdin is sys.stdin:
            try:
                return self.console.input(f"[bold #C084FC]{prompt_text}[/bold #C084FC]")
            except EOFError:
                raise
        line = self.stdin.readline()
        if not line:
            raise EOFError
        return line.rstrip("\r\n")
