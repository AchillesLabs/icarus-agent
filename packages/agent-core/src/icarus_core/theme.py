"""UI color themes and customizable palette management for Icarus Agent."""

from __future__ import annotations

import re
from dataclasses import dataclass

from icarus_core.config import ConfigManager


@dataclass(frozen=True)
class UITheme:
    """Represents a UI styling palette."""

    name: str
    primary: str  # Banner, mascot, active badges, prompt '>'
    border: str  # Card and box borders
    secondary: str  # Section headers, active text highlights
    prompt_ansi: str  # prompt-toolkit ANSI color for prompt
    description: str


PRESET_THEMES: dict[str, UITheme] = {
    "purple": UITheme(
        name="purple",
        primary="#C084FC",
        border="#A855F7",
        secondary="#E9D5FF",
        prompt_ansi="ansimagenta",
        description="Royal Cyber Purple (Default)",
    ),
    "cyan": UITheme(
        name="cyan",
        primary="#38BDF8",
        border="#0284C7",
        secondary="#BAE6FD",
        prompt_ansi="ansicyan",
        description="Electric Neon Cyan",
    ),
    "green": UITheme(
        name="green",
        primary="#4ADE80",
        border="#16A34A",
        secondary="#BBF7D0",
        prompt_ansi="ansigreen",
        description="Matrix Emerald Green",
    ),
    "amber": UITheme(
        name="amber",
        primary="#FBBF24",
        border="#D97706",
        secondary="#FEF08A",
        prompt_ansi="ansiyellow",
        description="Solar Gold & Amber",
    ),
    "red": UITheme(
        name="red",
        primary="#F87171",
        border="#DC2626",
        secondary="#FECACA",
        prompt_ansi="ansired",
        description="Ares Crimson Red",
    ),
    "blue": UITheme(
        name="blue",
        primary="#60A5FA",
        border="#2563EB",
        secondary="#BFDBFE",
        prompt_ansi="ansiblue",
        description="Deep Cobalt Blue",
    ),
    "pink": UITheme(
        name="pink",
        primary="#F472B6",
        border="#DB2777",
        secondary="#FBCFE8",
        prompt_ansi="ansimagenta",
        description="Neon Synthwave Pink",
    ),
}


def _create_custom_theme(hex_code: str) -> UITheme:
    """Generate a custom theme from an arbitrary hex color code."""
    clean_hex = hex_code.strip()
    if not clean_hex.startswith("#"):
        clean_hex = f"#{clean_hex}"

    clean_hex = clean_hex.upper()

    if not re.match(r"^#[0-9A-F]{6}$", clean_hex):
        raise ValueError(
            f"Invalid hex color code: '{hex_code}'. Must be in format #RRGGBB (e.g. #FF5500)."
        )

    return UITheme(
        name=clean_hex.lower(),
        primary=clean_hex,
        border=clean_hex,
        secondary="#FFFFFF",
        prompt_ansi="ansimagenta",
        description=f"Custom User Hex ({clean_hex})",
    )


def get_theme(theme_name: str | None = None) -> UITheme:
    """Retrieve the active UI theme, or a specific named theme/hex color."""
    if theme_name is None:
        try:
            cfg = ConfigManager().load_config()
            theme_name = cfg.theme
        except Exception:
            theme_name = "purple"

    clean = theme_name.strip()
    clean_lower = clean.lower()
    if clean_lower in PRESET_THEMES:
        return PRESET_THEMES[clean_lower]

    if clean.startswith("#") or re.match(r"^[0-9a-fA-F]{6}$", clean):
        return _create_custom_theme(clean)

    raise ValueError(
        f"Unknown UI theme '{theme_name}'. Choose from: {list(PRESET_THEMES.keys())} or provide a custom hex color (e.g. #FF5500)."
    )


def set_theme(theme_name: str) -> UITheme:
    """Validate, persist, and return the new active UI theme."""
    target_theme = get_theme(theme_name)
    mgr = ConfigManager()
    cfg = mgr.load_config()
    cfg.theme = target_theme.name
    mgr.save_config(cfg)
    return target_theme


def list_themes() -> dict[str, UITheme]:
    """Return all pre-configured preset themes."""
    return PRESET_THEMES.copy()
