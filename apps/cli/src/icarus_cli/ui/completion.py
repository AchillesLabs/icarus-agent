"""Interactive command completion and context-aware suggestions for Icarus terminal chat.

Uses prompt_toolkit Completer to provide live dynamic completion for slash commands,
subcommands, and arguments while keeping standard chat messages completely untouched.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field

from prompt_toolkit.completion import CompleteEvent, Completer, Completion
from prompt_toolkit.document import Document

logger = logging.getLogger("icarus.cli.completion")


@dataclass
class SlashCommandDef:
    """Metadata for an interactive slash command."""

    name: str
    description: str
    args_hint: str = ""
    subcommands: dict[str, str] = field(default_factory=dict)
    arg_completer: Callable[[list[str]], list[tuple[str, str]]] | None = None


def _get_toolset_names() -> list[str]:
    """Retrieve registered toolset category names."""
    try:
        from icarus_core.tools.toolsets import DEFAULT_TOOLSETS

        return list(DEFAULT_TOOLSETS.keys())
    except Exception:
        return ["core", "filesystem", "terminal", "web", "integrations", "code"]


def _get_enabled_toolset_names() -> list[str]:
    """Retrieve currently active toolset category names."""
    try:
        from icarus_core.tools.toolsets import ToolsetManager

        return ToolsetManager().load_active_toolsets()
    except Exception:
        return ["core", "filesystem", "terminal", "web"]


def _get_supported_integration_ids() -> list[str]:
    """Retrieve supported integration IDs."""
    try:
        from icarus_cli.integrations_cmd import AVAILABLE_MANIFESTS

        return list(AVAILABLE_MANIFESTS.keys())
    except Exception:
        return ["google", "github", "slack", "stripe"]


def _get_connected_integration_ids() -> list[str]:
    """Retrieve currently connected integrations with stored credentials."""
    try:
        from icarus_core.tools.auth import ToolAuthManager

        supported = _get_supported_integration_ids()
        return [p for p in supported if ToolAuthManager.has_token(p)]
    except Exception:
        return []


def _get_theme_names() -> list[str]:
    """Retrieve available UI theme names."""
    try:
        from icarus_core.theme import list_themes

        return list(list_themes().keys())
    except Exception:
        return ["amber", "cyan", "purple", "green", "red", "blue", "pink"]


def _get_available_models() -> list[str]:
    """Retrieve known models for active provider."""
    try:
        from icarus_core.config import ConfigManager
        from icarus_core.providers import fetch_provider_models

        cfg = ConfigManager().load_config()
        provider = cfg.default_provider or "groq"
        discovered = fetch_provider_models(provider)
        if discovered:
            return [m.id for m in discovered]
    except Exception:
        pass
    return [
        "llama-3.3-70b-versatile",
        "llama-3.1-8b-instant",
        "mixtral-8x7b-32768",
        "gemma2-9b-it",
    ]


def _complete_toolsets(args: list[str]) -> list[tuple[str, str]]:
    """Context-aware completion for /toolsets."""
    if not args or len(args) == 1:
        subcmds = [
            ("list", "Inspect all toolsets and active status"),
            ("enable", "Enable a modular toolset category"),
            ("disable", "Disable a modular toolset category"),
            ("reset", "Reset toolset configuration to default defaults"),
        ]
        prefix = args[0] if args else ""
        return [(cmd, desc) for cmd, desc in subcmds if cmd.startswith(prefix)]

    subaction = args[0].lower()
    prefix = args[1] if len(args) > 1 else ""

    if subaction == "enable":
        all_ts = _get_toolset_names()
        return [(ts, f"Enable '{ts}' toolset") for ts in all_ts if ts.startswith(prefix)]

    if subaction == "disable":
        active_ts = _get_enabled_toolset_names()
        return [(ts, f"Disable '{ts}' toolset") for ts in active_ts if ts.startswith(prefix)]

    return []


def _complete_integrations(args: list[str]) -> list[tuple[str, str]]:
    """Context-aware completion for /integrations."""
    if not args or len(args) == 1:
        subcmds = [
            ("connect", "Connect third-party account (OAuth / API Token)"),
            ("status", "Inspect active connection health and scopes"),
            ("disconnect", "Revoke authorization and delete stored credentials"),
            ("doctor", "Test live connectivity and token validity"),
        ]
        prefix = args[0] if args else ""
        return [(cmd, desc) for cmd, desc in subcmds if cmd.startswith(prefix)]

    subaction = args[0].lower()
    prefix = args[1] if len(args) > 1 else ""

    if subaction in ("connect", "doctor"):
        all_provs = _get_supported_integration_ids()
        return [
            (p, f"Provider '{p.title()}'")
            for p in all_provs
            if p.lower().startswith(prefix.lower())
        ]

    if subaction == "disconnect":
        connected = _get_connected_integration_ids()
        if not connected:
            connected = _get_supported_integration_ids()
        return [
            (p, f"Disconnect '{p.title()}'")
            for p in connected
            if p.lower().startswith(prefix.lower())
        ]

    return []


def _complete_models(args: list[str]) -> list[tuple[str, str]]:
    """Context-aware completion for /model."""
    prefix = args[0] if args else ""
    models = _get_available_models()
    return [(m, f"Model ID: {m}") for m in models if m.lower().startswith(prefix.lower())]


def _complete_themes(args: list[str]) -> list[tuple[str, str]]:
    """Context-aware completion for /theme."""
    prefix = args[0] if args else ""
    themes = _get_theme_names()
    return [(t, f"Color Palette '{t}'") for t in themes if t.lower().startswith(prefix.lower())]


def _complete_skills(args: list[str]) -> list[tuple[str, str]]:
    """Context-aware completion for /skills."""
    subcmds = [
        ("list", "List all workspace skills"),
        ("pull", "Pull skill from Git repository or URL"),
    ]
    prefix = args[0] if args else ""
    return [(cmd, desc) for cmd, desc in subcmds if cmd.startswith(prefix)]


def _complete_connect(args: list[str]) -> list[tuple[str, str]]:
    """Context-aware completion for /connect."""
    prefix = args[0] if args else ""
    providers = _get_supported_integration_ids()
    return [(p, f"Connect {p.title()}") for p in providers if p.lower().startswith(prefix.lower())]


# Master registry of interactive slash commands
SLASH_COMMANDS: dict[str, SlashCommandDef] = {
    "help": SlashCommandDef(
        name="help",
        description="Display all available in-chat slash commands and usage",
    ),
    "model": SlashCommandDef(
        name="model",
        description="Switch active LLM model or inspect active model",
        args_hint="[model_id]",
        arg_completer=_complete_models,
    ),
    "models": SlashCommandDef(
        name="models",
        description="View and select from all available models (Free vs Paid)",
    ),
    "toolsets": SlashCommandDef(
        name="toolsets",
        description="Manage modular toolsets (list, enable, disable, reset)",
        args_hint="<list|enable|disable|reset> [name]",
        arg_completer=_complete_toolsets,
    ),
    "connect": SlashCommandDef(
        name="connect",
        description="Connect third-party apps (Google, GitHub, Slack, Stripe)",
        args_hint="[provider]",
        arg_completer=_complete_connect,
    ),
    "integrations": SlashCommandDef(
        name="integrations",
        description="Manage third-party integrations (connect, status, disconnect, doctor)",
        args_hint="<connect|status|disconnect|doctor> [provider]",
        arg_completer=_complete_integrations,
    ),
    "tools": SlashCommandDef(
        name="tools",
        description="List registered tools or inspect parameter schema",
        args_hint="[tool_name]",
    ),
    "skills": SlashCommandDef(
        name="skills",
        description="Manage workspace skills or pull external skills",
        args_hint="<list|pull> [url]",
        arg_completer=_complete_skills,
    ),
    "theme": SlashCommandDef(
        name="theme",
        description="Change UI accent color theme",
        args_hint="[theme_name]",
        arg_completer=_complete_themes,
    ),
    "session": SlashCommandDef(
        name="session",
        description="Display active session details, message counts, and token totals",
    ),
    "clear": SlashCommandDef(
        name="clear",
        description="Clear the terminal screen buffer",
    ),
    "exit": SlashCommandDef(
        name="exit",
        description="Exit the interactive chat REPL session",
    ),
}


class IcarusSlashCompleter(Completer):
    """Context-aware command completer for prompt_toolkit.

    Activated strictly when the input begins with '/'.
    Normal user chat input, file paths, code, or URLs are never treated as commands.
    """

    def __init__(self, commands: dict[str, SlashCommandDef] | None = None) -> None:
        self.commands = commands or SLASH_COMMANDS

    def get_completions(
        self, document: Document, complete_event: CompleteEvent
    ) -> Iterable[Completion]:
        """Yield completion suggestions matching the current cursor position."""
        text_before_cursor = document.text_before_cursor

        # Only activate for slash commands starting with '/'
        if not text_before_cursor.startswith("/"):
            return

        # If user typed '//' (e.g. comment or protocol), do not suggest
        if text_before_cursor.startswith("//"):
            return

        command_line = text_before_cursor[1:]  # strip leading '/'
        parts = command_line.split(" ")

        # 1. User is typing the top-level slash command (e.g. "/" or "/to")
        if len(parts) == 1:
            cmd_prefix = parts[0].lower()
            for cmd_name, cmd_def in sorted(self.commands.items()):
                if cmd_name.startswith(cmd_prefix):
                    display_meta = cmd_def.description
                    hint = f" {cmd_def.args_hint}" if cmd_def.args_hint else ""
                    yield Completion(
                        text=cmd_name,
                        start_position=-len(cmd_prefix),
                        display=f"/{cmd_name}{hint}",
                        display_meta=display_meta,
                    )
            return

        # 2. User has typed a command and is typing subcommands/arguments (e.g. "/toolsets en")
        root_cmd = parts[0].lower()
        if root_cmd in self.commands:
            cmd_def = self.commands[root_cmd]
            if cmd_def.arg_completer is not None:
                args = parts[1:]
                current_word = args[-1]
                suggestions = cmd_def.arg_completer(args)
                for suggestion, desc in suggestions:
                    yield Completion(
                        text=suggestion,
                        start_position=-len(current_word),
                        display=suggestion,
                        display_meta=desc,
                    )
