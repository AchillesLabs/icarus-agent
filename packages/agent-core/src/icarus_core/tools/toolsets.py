"""Modular toolsets system for grouping, enabling, and disabling agent capabilities."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

from icarus_core.paths import get_icarus_home

logger = logging.getLogger("icarus.tools.toolsets")


@dataclass
class ToolsetDefinition:
    """Definition of a modular collection of tools."""

    name: str
    display_name: str
    description: str
    tools: list[str]
    is_default: bool = True
    tags: list[str] = field(default_factory=list)


# Standard toolset categories
DEFAULT_TOOLSETS: dict[str, ToolsetDefinition] = {
    "core": ToolsetDefinition(
        name="core",
        display_name="Core Utilities",
        description="Fundamental agent utilities including location, weather, and HTTP requests.",
        tools=["get_current_location", "get_weather", "http_request"],
        is_default=True,
        tags=["system", "utility"],
    ),
    "filesystem": ToolsetDefinition(
        name="filesystem",
        display_name="Filesystem Access",
        description="Local workspace file reading, writing, directory listing, and pattern search.",
        tools=["read_file", "write_file", "list_dir", "search", "search_files"],
        is_default=True,
        tags=["local", "io"],
    ),
    "web": ToolsetDefinition(
        name="web",
        display_name="Web & Research",
        description="Real-time internet search, safe webpage content fetching, and browser automation.",
        tools=["web_search", "fetch_webpage", "browser_navigate"],
        is_default=True,
        tags=["network", "browser"],
    ),
    "terminal": ToolsetDefinition(
        name="terminal",
        display_name="Terminal Execution",
        description="Subprocess shell command execution with safety policies and output truncation.",
        tools=["run_command"],
        is_default=True,
        tags=["execution", "shell"],
    ),
    "integrations": ToolsetDefinition(
        name="integrations",
        display_name="App Integrations",
        description="External third-party app connectors (Google Calendar, Gmail, Google Drive, GitHub, Slack, Stripe).",
        tools=[
            "gmail_search",
            "gmail_send",
            "calendar_events",
            "calendar_create_event",
            "drive_search",
            "drive_read_file",
            "github_issues",
            "github_create_issue",
            "slack_send_message",
            "stripe_payment_link",
        ],
        is_default=True,
        tags=["cloud", "oauth"],
    ),
    "mcp": ToolsetDefinition(
        name="mcp",
        display_name="Model Context Protocol (MCP)",
        description="Dynamic external tools discovered and served over stdio and SSE MCP servers.",
        tools=["*mcp*"],
        is_default=True,
        tags=["mcp", "extensible"],
    ),
    "automation": ToolsetDefinition(
        name="automation",
        display_name="Background Automation",
        description="Persistent reminders, background timers, and scheduled agent tasks.",
        tools=["schedule_reminder", "list_reminders"],
        is_default=True,
        tags=["scheduler", "background"],
    ),
    "memory": ToolsetDefinition(
        name="memory",
        display_name="Memory & Reflection",
        description="Long-term memory retrieval and agent skills evolution.",
        tools=["save_memory", "recall_memory"],
        is_default=True,
        tags=["memory", "knowledge"],
    ),
}


class ToolsetManager:
    """Manages active toolsets stored in ~/.icarus/toolsets.json."""

    def __init__(self, config_path: Path | None = None) -> None:
        self.config_path = config_path or (get_icarus_home() / "toolsets.json")
        self._toolsets: dict[str, ToolsetDefinition] = dict(DEFAULT_TOOLSETS)

    def get_config_file(self) -> Path:
        """Return the path to the toolsets configuration file."""
        return self.config_path

    def list_toolsets(self) -> list[ToolsetDefinition]:
        """Return all available toolset definitions."""
        return list(self._toolsets.values())

    def get_toolset(self, name: str) -> ToolsetDefinition | None:
        """Retrieve a toolset definition by name."""
        return self._toolsets.get(name.lower().strip())

    def load_active_toolsets(self) -> set[str]:
        """Load set of currently enabled toolset names from disk."""
        if not self.config_path.exists():
            # Default to all toolsets that have is_default=True
            return {name for name, ts in self._toolsets.items() if ts.is_default}

        try:
            content = self.config_path.read_text(encoding="utf-8")
            data = json.loads(content)
            if isinstance(data, dict) and "enabled" in data:
                return set(data["enabled"])
            if isinstance(data, list):
                return set(data)
        except Exception as exc:
            logger.warning("Failed to parse %s: %s; using defaults", self.config_path, exc)

        return {name for name, ts in self._toolsets.items() if ts.is_default}

    def save_active_toolsets(self, enabled: set[str] | list[str]) -> None:
        """Persist enabled toolsets list to disk."""
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "enabled": sorted(list(set(enabled))),
            "updated_at": None,
        }
        self.config_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def is_toolset_enabled(self, name: str) -> bool:
        """Return True if the specified toolset is active."""
        active = self.load_active_toolsets()
        return name.lower().strip() in active

    def enable_toolset(self, name: str) -> bool:
        """Enable a toolset by name. Returns True if successfully enabled."""
        norm_name = name.lower().strip()
        if norm_name not in self._toolsets:
            return False

        active = self.load_active_toolsets()
        active.add(norm_name)
        self.save_active_toolsets(active)
        return True

    def disable_toolset(self, name: str) -> bool:
        """Disable a toolset by name. Returns True if successfully disabled."""
        norm_name = name.lower().strip()
        if norm_name not in self._toolsets:
            return False

        active = self.load_active_toolsets()
        if norm_name in active:
            active.remove(norm_name)
            self.save_active_toolsets(active)
        return True

    def reset_defaults(self) -> None:
        """Reset enabled toolsets back to default configuration."""
        defaults = {name for name, ts in self._toolsets.items() if ts.is_default}
        self.save_active_toolsets(defaults)

    def is_tool_enabled(self, tool_name: str) -> bool:
        """Determine whether an individual tool name is permitted under the active toolsets."""
        active_toolsets = self.load_active_toolsets()

        # Check if tool is an MCP tool
        if tool_name.startswith("mcp_") or ":mcp:" in tool_name:
            return "mcp" in active_toolsets

        # Check which toolset contains this tool
        assigned_toolset: str | None = None
        for ts_name, ts_def in self._toolsets.items():
            if tool_name in ts_def.tools:
                assigned_toolset = ts_name
                break

        # If tool is assigned to a toolset, check if that toolset is active
        if assigned_toolset is not None:
            return assigned_toolset in active_toolsets

        # If tool is ungrouped or custom plugin, default to allowed unless explicitly disabled
        return True
