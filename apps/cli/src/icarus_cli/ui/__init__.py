"""Icarus CLI Terminal User Interface (TUI) and presentation component suite."""

from icarus_cli.ui.approvals import (
    format_action_preview,
    prompt_for_approval,
    render_approval_prompt,
)
from icarus_cli.ui.branding import (
    ICARUS_COMPACT_LOGO,
    ICARUS_EMBLEM_ART,
    ICARUS_LOGO_ASCII,
    ICARUS_PLAIN_EMBLEM,
    ICARUS_PLAIN_LOGO,
    get_ascii_logo,
    get_banner,
    get_compact_logo,
    get_sprite,
    render_banner,
    render_logo,
)
from icarus_cli.ui.completion import SLASH_COMMANDS, IcarusSlashCompleter, SlashCommandDef
from icarus_cli.ui.formatters import (
    render_empty_state,
    render_error,
    render_key_value_panel,
    render_section_header,
    render_success,
    render_warning,
)
from icarus_cli.ui.status import format_status_bar, render_status_bar

__all__ = [
    "ICARUS_COMPACT_LOGO",
    "ICARUS_EMBLEM_ART",
    "ICARUS_LOGO_ASCII",
    "ICARUS_PLAIN_EMBLEM",
    "ICARUS_PLAIN_LOGO",
    "SLASH_COMMANDS",
    "IcarusSlashCompleter",
    "SlashCommandDef",
    "format_action_preview",
    "format_status_bar",
    "get_ascii_logo",
    "get_banner",
    "get_compact_logo",
    "get_sprite",
    "prompt_for_approval",
    "render_approval_prompt",
    "render_banner",
    "render_empty_state",
    "render_error",
    "render_key_value_panel",
    "render_logo",
    "render_section_header",
    "render_status_bar",
    "render_success",
    "render_warning",
]
