"""Status bar components and responsive formatting for Icarus terminal sessions."""

from __future__ import annotations

from typing import Any

from icarus_core.theme import UITheme, get_theme
from rich.console import Console


def format_status_bar(
    model: str,
    provider: str,
    session_id: str | None = None,
    tokens_used: int = 0,
    token_budget: int = 128000,
    toolset_info: str | None = None,
    mode: str | None = None,
    width: int = 80,
    theme: UITheme | None = None,
    plain: bool = False,
) -> str:
    """Format a responsive, single-line terminal status bar matching the current width.

    Fields are prioritized:
    - High priority: App name, active model.
    - Medium priority: Provider, context token usage %, session ID.
    - Low priority: Token counts, toolset profile, state badges.
    """
    th = theme or get_theme()
    short_session = session_id[:8] if session_id else "new"
    pct = (tokens_used / token_budget * 100) if (token_budget and token_budget > 0) else 0.0

    # Truncate model name if needed
    clean_model = model.split("/")[-1]

    # Ultra-narrow width (< 50 columns): minimal essential indicators
    if width < 50:
        if len(clean_model) > 14:
            clean_model = clean_model[:12] + ".."
        if plain:
            return f"Icarus | {clean_model} | {pct:.0f}%"
        return (
            f"[bold {th.primary}]Icarus[/bold {th.primary}] [dim]│[/dim] "
            f"[bold white]{clean_model}[/bold white] [dim]│[/dim] "
            f"[dim]{pct:.0f}%[/dim]"
        )

    # Compact width (50 - 74 columns): model, provider, %, session
    if width < 75:
        if len(clean_model) > 16:
            clean_model = clean_model[:14] + ".."
        if plain:
            return f"Icarus | {provider.title()} · {clean_model} | {pct:.0f}% | {short_session}"
        return (
            f"[bold {th.primary}]Icarus[/bold {th.primary}] [dim]│[/dim] "
            f"[bold white]{provider.title()} · {clean_model}[/bold white] [dim]│[/dim] "
            f"[dim]Context {pct:.0f}%[/dim] [dim]│[/dim] "
            f"[dim]{short_session}[/dim]"
        )

    # Standard width (75 - 105 columns): standard full status bar
    if width < 105:
        tools_part = f" [dim]│[/dim] [dim]{toolset_info}[/dim]" if toolset_info else ""
        if plain:
            tools_plain = f" | {toolset_info}" if toolset_info else ""
            return f"Icarus | {provider.title()} · {clean_model} | Context {pct:.0f}% | Session {short_session}{tools_plain}"
        return (
            f"[bold {th.primary}]Icarus[/bold {th.primary}] [dim]│[/dim] "
            f"[bold white]{provider.title()} · {clean_model}[/bold white] [dim]│[/dim] "
            f"[dim]Context {pct:.0f}%[/dim] [dim]│[/dim] "
            f"[dim]Session {short_session}[/dim]{tools_part}"
        )

    # Wide terminal (>= 105 columns): detailed metrics
    tools_part = f" [dim]│[/dim] [dim]Tools: {toolset_info}[/dim]" if toolset_info else ""
    token_str = f"{tokens_used:,} / {token_budget:,}" if tokens_used > 0 else "0 tokens"
    if plain:
        tools_plain = f" | Tools: {toolset_info}" if toolset_info else ""
        return f"Icarus | {provider.title()} · {clean_model} | Context {pct:.1f}% ({token_str}) | Session {short_session}{tools_plain}"
    return (
        f"[bold {th.primary}]Icarus[/bold {th.primary}] [dim]│[/dim] "
        f"[bold white]{provider.title()} · {clean_model}[/bold white] [dim]│[/dim] "
        f"[dim]Context {pct:.1f}% ({token_str})[/dim] [dim]│[/dim] "
        f"[dim]Session {short_session}[/dim]{tools_part} [dim]│[/dim] "
        f"[dim]/help for commands[/dim]"
    )


def render_status_bar(
    console: Console | None = None,
    model: str = "default",
    provider: str = "local",
    session_id: str | None = None,
    tokens_used: int = 0,
    token_budget: int = 128000,
    toolset_info: str | None = None,
    mode: str | None = None,
    theme: UITheme | None = None,
    **kwargs: Any,
) -> None:
    """Print the formatted status bar to console if running in an interactive terminal."""
    cons = console or kwargs.get("console") or Console()
    try:
        # If redirected or non-interactive, do not pollute output
        if not cons.is_terminal:
            return
    except Exception:
        pass

    width = cons.width or 80
    bar = format_status_bar(
        model=model,
        provider=provider,
        session_id=session_id,
        tokens_used=tokens_used,
        token_budget=token_budget,
        toolset_info=toolset_info,
        mode=mode,
        width=width,
        theme=theme,
    )
    cons.print(bar)
