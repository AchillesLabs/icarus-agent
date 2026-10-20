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
from icarus_core.theme import UITheme, get_theme
from prompt_toolkit import PromptSession
from prompt_toolkit.completion import Completer
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.history import FileHistory
from prompt_toolkit.key_binding import KeyBindings, KeyPressEvent
from prompt_toolkit.styles import Style
from rich.console import Console

from icarus_cli.ui.branding import (
    ICARUS_EMBLEM_ART,
    ICARUS_LOGO_ASCII,
)
from icarus_cli.ui.branding import (
    get_banner as _ui_get_banner,
)
from icarus_cli.ui.branding import (
    get_sprite as _ui_get_sprite,
)
from icarus_cli.ui.branding import (
    render_banner as _ui_render_banner,
)
from icarus_cli.ui.completion import IcarusSlashCompleter

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
        matching standard CLI behavior.
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


BANNER_ART = ICARUS_LOGO_ASCII
SPRITE_ART = ICARUS_EMBLEM_ART


def get_banner(theme: UITheme | None = None) -> str:
    return _ui_get_banner(theme=theme)


def get_sprite(theme: UITheme | None = None) -> str:
    return _ui_get_sprite(theme=theme)


ICARUS_BANNER = get_banner()
ICARUS_SPRITE = get_sprite()


def render_workspace_header(
    console: Console,
    model: str,
    provider: str,
    session_id: str,
    tokens_used: int = 0,
    token_budget: int = 128000,
    mode: str = "Autonomous Personal Agent",
    remote_url: str | None = None,
    theme: UITheme | None = None,
    no_banner: bool = False,
) -> None:
    """Render the top status dashboard with customizable theme accent and dynamic skills."""
    _ui_render_banner(
        console=console,
        model=model,
        provider=provider,
        session_id=session_id,
        tokens_used=tokens_used,
        token_budget=token_budget,
        mode=mode,
        remote_url=remote_url,
        theme=theme,
        no_banner=no_banner,
    )


def get_history_file() -> Path:
    """Return the path to the persistent CLI chat history file."""
    history_dir = get_icarus_home()
    history_dir.mkdir(parents=True, exist_ok=True)
    return history_dir / "history"


class InteractivePrompt:
    """Wraps prompt_toolkit.PromptSession with persistent history, completion, and keybindings.

    Falls back cleanly to console.input or stdin in non-interactive/test environments.
    """

    def __init__(
        self,
        console: Console | None = None,
        stdin: TextIO | None = None,
        history_file: Path | None = None,
        theme: UITheme | None = None,
        completer: Completer | None = None,
    ) -> None:
        self.console = console or Console()
        self.stdin = stdin or sys.stdin
        self.history_path = history_file or get_history_file()
        self.theme = theme or get_theme()
        self.completer = completer if completer is not None else IcarusSlashCompleter()
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
        """Initialize prompt_toolkit PromptSession with custom keybindings and autocomplete."""
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

        style = Style.from_dict(
            {
                "completion-menu.completion": "bg:#1e1e2e #cdd6f4",
                "completion-menu.completion.current": "bg:#f59e0b #11111b bold",
                "completion-menu.meta.completion": "bg:#181825 #a6adc8",
                "completion-menu.meta.completion.current": "bg:#d97706 #11111b",
                "scrollbar.background": "bg:#11111b",
                "scrollbar.button": "bg:#45475a",
            }
        )

        try:
            self._session = PromptSession(
                history=FileHistory(str(self.history_path)),
                key_bindings=kb,
                completer=self.completer,
                complete_while_typing=True,
                style=style,
            )
        except Exception:
            self._session = None

    def read_input(self, prompt_text: str = "> ", rprompt_text: str | None = None) -> str:
        """Read a line of user input, supporting interactive prompt_toolkit or fallback."""
        if self._session is not None and self.is_interactive:
            formatted_prompt = HTML(
                f"<b><{self.theme.prompt_ansi}>{prompt_text}</{self.theme.prompt_ansi}></b>"
            )
            rprompt = HTML(f"<ansigray>{rprompt_text}</ansigray>") if rprompt_text else None
            return self._session.prompt(formatted_prompt, rprompt=rprompt)

        # Fallback for non-interactive runners or redirected stdin
        if hasattr(self.console, "input") and self.stdin is sys.stdin:
            try:
                return self.console.input(
                    f"[bold {self.theme.primary}]{prompt_text}[/bold {self.theme.primary}]"
                )
            except EOFError:
                raise
        line = self.stdin.readline()
        if not line:
            raise EOFError
        return line.rstrip("\r\n")


# Alias for backwards compatibility
IcarusInputPrompt = InteractivePrompt
