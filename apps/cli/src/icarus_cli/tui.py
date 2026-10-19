"""Terminal User Interface (TUI) workspace components for Icarus Agent.

Provides alternate screen buffer transitions (\033[?1049h / \033[?1049l),
pinned status header bars, and prompt_toolkit interactive sessions with
persistent history and keybindings.
"""

from __future__ import annotations

import getpass
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
        """Return True if alternate screen buffer should be activated."""
        if self.force:
            return True
        try:
            return hasattr(self.stream, "isatty") and self.stream.isatty()
        except Exception:
            return False

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


ICARUS_SPRITE = """[bold gold1]
             ▄█▄
   █▄       █████       ▄█
   ███▄   ▄██ █ ██▄   ▄███
   ▀████▄███████████▄████▀
     ▀██████ ▀█▀ ██████▀
        ▀█████████▀
            ▀█▀
[/bold gold1]"""


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
    """Render the pinned top status dashboard of the terminal workspace."""
    pct = (tokens_used / token_budget * 100) if token_budget > 0 else 0.0

    try:
        user = getpass.getuser().capitalize()
    except Exception:
        user = "Explorer"

    try:
        cwd = str(Path.cwd().resolve())
    except Exception:
        cwd = "Workspace"

    status_badge = (
        f"[bold cyan]REMOTE ({remote_url})[/bold cyan]"
        if remote_url
        else "[bold green]LOCAL RUNTIME[/bold green]"
    )
    tokens_info = (
        f"[bold white]Tokens:[/bold white] [bold yellow]{tokens_used:,}[/bold yellow] / "
        f"[dim]{token_budget:,}[/dim] [dim]({pct:.1f}%)[/dim]"
    )

    left_content = (
        f"[bold white]Welcome back, {user}![/bold white]\n"
        + ICARUS_SPRITE
        + f"\n[bold cyan]Model:[/bold cyan] [bold yellow]{model}[/bold yellow] [dim]({provider})[/dim]\n"
        + f"[dim]Session: {session_id}[/dim]\n"
        + f"[dim]Dir: {cwd}[/dim]"
    )

    right_content = (
        f"[bold gold1]Status:[/bold gold1] {status_badge}  •  {tokens_info}\n\n"
        "[bold gold1]Tips for getting started[/bold gold1]\n"
        '[dim]•[/dim] [white]Near me:[/white] [italic]"Find affordable hotels near me"[/italic]\n'
        '[dim]•[/dim] [white]Live web:[/white] [italic]"Search latest news on AI agents"[/italic]\n'
        '[dim]•[/dim] [white]Reminders:[/white] [italic]"Remind me in 30 mins to take a break"[/italic]\n\n'
        "[bold gold1]In-Chat Commands[/bold gold1]\n"
        "[bold cyan]/models[/bold cyan] Switch active model   [bold cyan]/doctor[/bold cyan] Diagnostics\n"
        "[bold cyan]/clear[/bold cyan]  Clear screen           [bold cyan]/exit[/bold cyan]   Save & quit"
    )

    table = Table.grid(expand=True, padding=(0, 2))
    table.add_column(ratio=5)
    table.add_column(ratio=6)
    table.add_row(left_content, right_content)

    header_title = (
        f"[bold gold1]* ICARUS AGENT CHAT[/bold gold1] [dim]v{__version__}[/dim] | "
        f"[bold magenta]{mode}[/bold magenta]"
    )
    header_subtitle = (
        "[dim]Chief of Staff • Live Web Intelligence • MCP Protocol • 24/7 Scheduler[/dim]"
    )

    panel = Panel(
        table,
        title=header_title,
        subtitle=header_subtitle,
        border_style="gold1",
        padding=(1, 2),
    )
    console.print(panel)


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
        """Initialize prompt_toolkit PromptSession with custom keybindings and toolbar."""
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

        def _bottom_toolbar() -> HTML:
            return HTML(
                " <b>[Ctrl+C]</b> Cancel Turn  │  "
                "<b>[Ctrl+D /exit]</b> Quit  │  "
                "<b>[/help]</b> Commands  │  "
                "<b>[/models]</b> Switch Model "
            )

        try:
            self._session = PromptSession(
                history=FileHistory(str(self.history_path)),
                key_bindings=kb,
                bottom_toolbar=_bottom_toolbar,
            )
        except Exception:
            self._session = None

    def read_input(self, prompt_text: str = "icarus ❯ ") -> str:
        """Read a line of user input, supporting interactive prompt_toolkit or fallback."""
        if self._session is not None and self.is_interactive:
            return self._session.prompt(HTML(f"<b><ansicyan>{prompt_text}</ansicyan></b>"))

        # Fallback for non-interactive runners or redirected stdin
        if hasattr(self.console, "input") and self.stdin is sys.stdin:
            try:
                return self.console.input(f"[bold cyan]{prompt_text}[/bold cyan]")
            except EOFError:
                raise
        line = self.stdin.readline()
        if not line:
            raise EOFError
        return line.rstrip("\r\n")
