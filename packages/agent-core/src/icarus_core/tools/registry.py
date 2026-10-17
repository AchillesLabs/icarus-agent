"""Extensible tool registry for registering and dispatching agent tools."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from icarus_contracts.tools import ToolCall, ToolDefinition, ToolResult

from icarus_core.tools.base import BaseTool
from icarus_core.tools.filesystem import ListDirTool, ReadFileTool
from icarus_core.tools.search import SearchTool


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


def create_default_registry() -> ToolRegistry:
    """Instantiate and configure the default ToolRegistry with built-in core tools."""
    registry = ToolRegistry()
    registry.register(ReadFileTool())
    registry.register(ListDirTool())
    registry.register(SearchTool())
    return registry
