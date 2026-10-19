"""Terminal User Interface (TUI) workspace components for Icarus Agent.

Provides alternate screen buffer transitions (\033[?1049h / \033[?1049l),
pinned status header bars, and prompt_toolkit interactive sessions with
persistent history and keybindings.
"""

from __future__ import annotations

import shutil
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
 ▄█▄        ▄█▄        ▄█▄
█████▄  ▄█████████▄  ▄█████
▀█████████████████████████▀
  ▀███████ ▀███▀ ███████▀
    ▀████   ▀█▀   ████▀
       ▀██   █   ██▀
          ▀  █  ▀
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
    """Render the top status dashboard of the terminal workspace."""
    pct = (tokens_used / token_budget * 100) if token_budget > 0 else 0.0

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

    right_content = (
        f"[bold white]ICARUS AGENT CHAT[/bold white] [bold gold1]v{__version__}[/bold gold1]\n"
        f"[bold cyan]{model}[/bold cyan] [dim]·[/dim] [yellow]{provider}[/yellow]  [dim]•  Session: {session_id}[/dim]\n"
        f"[dim]{cwd}[/dim]\n\n"
        f"[dim]Runtime:[/dim] {status_badge}   {tokens_info}\n"
        f"[dim]{mode}[/dim]\n"
        "[dim]Shortcuts:[/dim] [bold cyan]Ctrl+C[/bold cyan] Cancel  [dim]·[/dim]  "
        "[bold cyan]Ctrl+D /exit[/bold cyan] Quit  [dim]·[/dim]  "
        "[bold cyan]/help[/bold cyan] Commands  [dim]·[/dim]  "
        "[bold cyan]/models[/bold cyan] Switch Model"
    )

    table = Table.grid(padding=(0, 2))
    table.add_column()
    table.add_column()
    table.add_row(ICARUS_SPRITE.strip("\n"), right_content)

    boxed_header = Panel(
        table,
        border_style="cyan",
        title="[bold gold1]⚔ Achilles Vanguard[/bold gold1]",
        subtitle="[dim]CLI Autonomous Personal Agent[/dim]",
        padding=(1, 2),
    )

    console.print()
    console.print(boxed_header)
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
            cols = shutil.get_terminal_size().columns
            divider = "─" * max(10, cols - 1)
            formatted_prompt = HTML(
                f"<ansigray>{divider}</ansigray>\n<b><ansicyan>{prompt_text}</ansicyan></b>"
            )
            rprompt = HTML(f"<ansigray>{rprompt_text}</ansigray>") if rprompt_text else None
            return self._session.prompt(formatted_prompt, rprompt=rprompt)

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
