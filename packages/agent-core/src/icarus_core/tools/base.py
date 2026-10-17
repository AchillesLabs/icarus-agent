"""Base tool abstraction and interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from icarus_contracts.tools import ToolDefinition, ToolResult


class BaseTool(ABC):
    """Abstract base class for all callable agent tools."""

    @property
    @abstractmethod
    def definition(self) -> ToolDefinition:
        """Return tool metadata, parameter schema, and safety category."""
        ...

    @property
    def name(self) -> str:
        """Helper returning the name of the tool."""
        return self.definition.name

    @abstractmethod
    def execute(
        self,
        arguments: dict[str, Any],
        workspace_root: Path | str,
        call_id: str = "direct_call",
    ) -> ToolResult:
        """Execute the tool synchronously with arguments within workspace root."""
        ...
