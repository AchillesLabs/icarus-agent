"""Original Icarus terminal brand identity, ASCII artwork, and responsive banners.

Inspired by flight, wings, the sun, and intelligent automation.
Designed for clean rendering across standard 40, 60, 80, and 120 column terminals.
"""

from __future__ import annotations

from pathlib import Path

from icarus_core.theme import UITheme, get_theme
from rich.console import Console, RenderableType
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from icarus_cli import __version__

# Canonical Icarus ASCII Logo based on flight, wings, and solar identity
ICARUS_LOGO_ASCII = r"""       _  _____
      (_)/ ___/
     / // /__
    / / \___/
   /_/  I C A R U S

    YOUR PERSONAL AI RUNTIME"""

# Clean compact flight wing glyph and logo
ICARUS_COMPACT_LOGO = "  [☼] I C A R U S  •  Personal AI Runtime"
ICARUS_PLAIN_LOGO = "   I C A R U S  -  Personal AI Runtime"

# Solar flight emblem
ICARUS_EMBLEM_ART = r"""       ▄▄   ▄   ▄▄
     ▄███▀ ▄█▄ ▀███▄
 ▄▄ ▄███▀ ▄███▄ ▀███▄ ▄▄
  ▀████▄▄███████▄▄████▀
   ▀█████████████████▀
     ▀█████████████▀
        ▀███████▀
           ▀█▀"""

ICARUS_PLAIN_EMBLEM = r"""       \   |   /
     -- ( ☼ ) --
       /   |   \
      / \_ _/ \
     /_/  V  \_/"""


def get_ascii_logo(plain: bool = False) -> str:
    """Return raw ASCII logo string."""
    return ICARUS_LOGO_ASCII


def get_compact_logo(plain: bool = False) -> str:
    """Return compact single-line logo."""
    return ICARUS_PLAIN_LOGO if plain else ICARUS_COMPACT_LOGO


def get_banner(theme: UITheme | None = None, plain: bool = False) -> str:
    """Return styled or plain banner string for backward compatibility."""
    if plain:
        return ICARUS_LOGO_ASCII
    th = theme or get_theme()
    return f"[bold {th.primary}]{ICARUS_LOGO_ASCII}[/bold {th.primary}]"


def get_sprite(theme: UITheme | None = None, plain: bool = False) -> str:
    """Return styled or plain flight emblem for backward compatibility."""
    if plain:
        return ICARUS_PLAIN_EMBLEM
    th = theme or get_theme()
    return f"[bold {th.primary}]{ICARUS_EMBLEM_ART}[/bold {th.primary}]"


def render_logo(
    console: Console | None = None,
    compact: bool = False,
    plain: bool = False,
    theme: UITheme | None = None,
) -> None:
    """Render the Icarus brand logo to the given console."""
    cons = console or Console()
    th = theme or get_theme()

    if compact:
        if plain:
            cons.print(ICARUS_PLAIN_LOGO)
        else:
            cons.print(f"[bold {th.primary}]{ICARUS_COMPACT_LOGO}[/bold {th.primary}]")
        return

    if plain:
        cons.print(ICARUS_LOGO_ASCII)
    else:
        text = Text(ICARUS_LOGO_ASCII, style=f"bold {th.primary}")
        cons.print(text)


def render_banner(
    console: Console | None = None,
    model: str = "default",
    provider: str = "local",
    session_id: str | None = None,
    tokens_used: int = 0,
    token_budget: int = 128000,
    mode: str = "Autonomous Personal Agent",
    remote_url: str | None = None,
    theme: UITheme | None = None,
    compact: bool = False,
    plain: bool = False,
    no_banner: bool = False,
) -> None:
    """Render the full responsive Icarus startup workspace banner.

    Gracefully adapts layout across 40, 60, 80, and 120 column terminals.
    """
    if no_banner:
        return

    cons = console or Console()
    th = theme or get_theme()
    term_width = cons.width or 80

    pct = (tokens_used / token_budget * 100) if token_budget > 0 else 0.0

    try:
        cwd = str(Path.cwd().resolve())
    except Exception:
        cwd = "Workspace"

    # Truncate cwd if too long for terminal
    max_cwd_len = max(20, term_width - 30)
    cwd_display = "..." + cwd[-(max_cwd_len - 3) :] if len(cwd) > max_cwd_len else cwd

    # Skills discovery
    skills_line = "None loaded (.agents/skills/)"
    try:
        from icarus_core.skills import discover_skills

        discovered_skills = discover_skills(Path.cwd())
        if discovered_skills:
            skill_names = [s.name for s in discovered_skills]
            if len(skill_names) <= 3:
                skills_preview = ", ".join(skill_names)
            else:
                skills_preview = f"{', '.join(skill_names[:3])}, +{len(skill_names) - 3} more"
            skills_line = f"{skills_preview} ({len(discovered_skills)} skills)"
    except Exception:
        pass

    short_session = session_id[:8] if session_id else "new"

    # In plain mode, print clean non-bordered text
    if plain:
        cons.print(ICARUS_LOGO_ASCII)
        cons.print(f"Model: {model} ({provider}) | Session: {short_session}")
        cons.print(f"Path:  {cwd_display}")
        cons.print("Commands: /help, /tools, /connect, /skills, /theme, /exit")
        cons.print()
        return

    # Compact mode for repeated turns or user flag
    if compact or term_width < 50:
        cons.print()
        cons.print(f"[bold {th.primary}]{ICARUS_COMPACT_LOGO}[/bold {th.primary}]")
        cons.print(
            f"[dim]Model:[/dim] [bold white]{model}[/bold white] [dim]({provider})[/dim]  "
            f"[dim]Session:[/dim] [dim]{short_session}[/dim]"
        )
        cons.print(
            f"[dim]Type [bold {th.primary}]/help[/bold {th.primary}] for slash commands or enter your prompt below.[/dim]\n"
        )
        return

    # Information table
    info_table = Table.grid(padding=(0, 2))
    info_table.add_column(style=f"bold {th.primary}", width=7)
    info_table.add_column()

    info_table.add_row("Model", f"[bold white]{model}[/bold white] [dim]({provider})[/dim]")
    info_table.add_row("Path", f"[dim]{cwd_display}[/dim]")
    info_table.add_row("Session", f"[dim]{session_id or 'new'}[/dim]")
    info_table.add_row("Tools", "[dim]file, web, gmail, calendar, api, shell (21 tools)[/dim]")
    info_table.add_row("Skills", f"[dim]{skills_line}[/dim]")
    info_table.add_row(
        "Cmds",
        f"[dim][bold {th.primary}]/help[/bold {th.primary}] · /tools · /connect · /skills · /theme · /exit[/dim]",
    )

    # Status badge
    status_badge = (
        f"[bold cyan]REMOTE ({remote_url})[/bold cyan]"
        if remote_url
        else f"[bold {th.primary}]LOCAL RUNTIME[/bold {th.primary}]"
    )
    tokens_info = (
        f"[bold {th.secondary}]{tokens_used:,}[/bold {th.secondary}] / "
        f"[dim]{token_budget:,}[/dim] [dim]({pct:.1f}%)[/dim]"
    )

    # Responsive grid layout:
    # >= 70 cols: side-by-side logo/emblem + info table
    # < 70 cols: vertically stacked so table columns never wrap awkwardly
    if term_width >= 70:
        main_grid = Table.grid(padding=(0, 2))
        main_grid.add_column(width=26)
        main_grid.add_column()
        main_grid.add_row(get_sprite(th), info_table)
        content: RenderableType = main_grid
    else:
        main_grid = Table.grid(padding=(0, 1))
        main_grid.add_row(get_sprite(th))
        main_grid.add_row(info_table)
        content = main_grid

    panel = Panel(
        content,
        border_style=th.border,
        title=f"[bold {th.secondary}]─── ICARUS AGENT CHAT v{__version__} ───[/bold {th.secondary}]",
        subtitle=f"[dim]{mode}  •  {status_badge}  •  {tokens_info}[/dim]",
        padding=(0, 1),
    )

    cons.print()
    cons.print(Text(ICARUS_LOGO_ASCII, style=f"bold {th.primary}"))
    cons.print()
    cons.print(panel)
    cons.print(
        f"[dim]Welcome to Icarus Agent! Type your message or [bold {th.primary}]/help[/bold {th.primary}] for commands.[/dim]"
    )
    cons.print(
        "[dim]* Tip: Icarus can search live flights, weather, compare prices, edit code, and manage tasks.[/dim]"
    )
    cons.print()
