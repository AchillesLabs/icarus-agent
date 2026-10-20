"""Extensible tool registry for registering and dispatching agent tools."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from icarus_contracts.tools import ToolCall, ToolDefinition, ToolResult

from icarus_core.tools.base import BaseTool
from icarus_core.tools.command import RunCommandTool
from icarus_core.tools.filesystem import ListDirTool, ReadFileTool, WriteFileTool
from icarus_core.tools.location import GetCurrentLocationTool
from icarus_core.tools.search import SearchTool
from icarus_core.tools.web import FetchWebpageTool, WebSearchTool


class ToolRegistry:
    """Registry managing available tool instances and dispatching invocations."""

    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        """Register a new tool instance in the registry."""
        self._tools[tool.name] = tool

    def get(self, name: str) -> BaseTool | None:
        """Retrieve a registered tool by name."""
        return self._tools.get(name)

    def has(self, name: str) -> bool:
        """Check if a tool is registered."""
        return name in self._tools

    def list_tools(self) -> list[ToolDefinition]:
        """Return definitions for all registered tools."""
        return [tool.definition for tool in self._tools.values()]

    def export_schemas(self) -> list[dict[str, Any]]:
        """Export OpenAI-compatible function schemas for all registered tools."""
        return [tool.definition.to_openai_schema() for tool in self._tools.values()]

    def execute(
        self,
        tool_call: ToolCall,
        workspace_root: Path | str,
    ) -> ToolResult:
        """Dispatch a ToolCall to its registered handler and return ToolResult."""
        tool = self.get(tool_call.name)
        if tool is None:
            return ToolResult(
                call_id=tool_call.id,
                name=tool_call.name,
                output="",
                error=f"Tool '{tool_call.name}' not found.",
                exit_code=1,
            )

        args = tool_call.get_arguments_dict()
        return tool.execute(arguments=args, workspace_root=workspace_root, call_id=tool_call.id)


def create_default_registry(
    load_mcp: bool = True,
    hosted_mode: bool = False,
    sandbox: Any | None = None,
    apply_toolset_filter: bool = False,
    active_toolsets: set[str] | list[str] | None = None,
) -> ToolRegistry:
    """Instantiate and configure the default ToolRegistry with built-in core tools and MCP servers."""
    registry = ToolRegistry()
    registry.register(ReadFileTool())
    registry.register(ListDirTool())
    registry.register(SearchTool())
    registry.register(WriteFileTool())
    registry.register(RunCommandTool(hosted_mode=hosted_mode, sandbox=sandbox))
    registry.register(WebSearchTool())
    registry.register(FetchWebpageTool())
    registry.register(GetCurrentLocationTool())

    try:
        from icarus_core.tools.browser import BrowserNavigateTool
        from icarus_core.tools.calendar import CalendarCreateEventTool, CalendarEventsTool
        from icarus_core.tools.drive import DriveReadFileTool, DriveSearchTool
        from icarus_core.tools.github import GithubCreateIssueTool, GithubIssuesTool
        from icarus_core.tools.gmail import GmailSearchTool, GmailSendTool
        from icarus_core.tools.http import HttpRequestTool
        from icarus_core.tools.slack import SlackSendMessageTool
        from icarus_core.tools.stripe import StripePaymentLinkTool
        from icarus_core.tools.weather import GetWeatherTool

        registry.register(HttpRequestTool())
        registry.register(GetWeatherTool())
        registry.register(BrowserNavigateTool())
        registry.register(GmailSearchTool())
        registry.register(GmailSendTool())
        registry.register(CalendarEventsTool())
        registry.register(CalendarCreateEventTool())
        registry.register(DriveSearchTool())
        registry.register(DriveReadFileTool())
        registry.register(GithubIssuesTool())
        registry.register(GithubCreateIssueTool())
        registry.register(SlackSendMessageTool())
        registry.register(StripePaymentLinkTool())
    except Exception:
        pass

    try:
        from icarus_core.tools.reminders import ListRemindersTool, ScheduleReminderTool

        registry.register(ScheduleReminderTool())
        registry.register(ListRemindersTool())
    except Exception:
        pass

    # Determine whether MCP tools should be loaded
    should_load_mcp = load_mcp
    if apply_toolset_filter:
        from icarus_core.tools.toolsets import ToolsetManager

        mgr = ToolsetManager()
        active = set(active_toolsets) if active_toolsets is not None else mgr.load_active_toolsets()
        if "mcp" not in active:
            should_load_mcp = False

    if should_load_mcp:
        try:
            from icarus_core.mcp.config import load_configured_mcp_servers_sync

            load_configured_mcp_servers_sync(registry, timeout=5.0)
        except Exception:
            pass

    if apply_toolset_filter:
        from icarus_core.tools.toolsets import ToolsetManager

        mgr = ToolsetManager()
        if active_toolsets is not None:
            active_set = set(active_toolsets)

            def is_allowed(tool_name: str) -> bool:
                if tool_name.startswith("mcp_") or ":mcp:" in tool_name:
                    return "mcp" in active_set
                for ts_name, ts_def in mgr._toolsets.items():
                    if tool_name in ts_def.tools:
                        return ts_name in active_set
                return True

        else:
            is_allowed = mgr.is_tool_enabled

        filtered_registry = ToolRegistry()
        for tool_name, tool_inst in list(registry._tools.items()):
            if is_allowed(tool_name):
                filtered_registry.register(tool_inst)
        return filtered_registry

    return registry
