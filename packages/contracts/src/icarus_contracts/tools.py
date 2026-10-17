"""Contracts and schemas for agent tools, definitions, calls, and results."""

from __future__ import annotations

import json
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from icarus_contracts.provider import PromptMessage
from icarus_contracts.session import MessageRole


class ToolSafetyCategory(StrEnum):
    """Safety classification governing tool execution policy."""

    SAFE_READ = "safe_read"
    REQUIRES_APPROVAL = "requires_approval"


class ToolDefinition(BaseModel):
    """Metadata and parameter schema representing a tool callable by the model."""

    name: str
    description: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    safety_category: ToolSafetyCategory = ToolSafetyCategory.SAFE_READ

    def to_openai_schema(self) -> dict[str, Any]:
        """Format definition into standard OpenAI-compatible function schema."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class ToolCall(BaseModel):
    """Normalized tool invocation request parsed from model completion."""

    id: str
    name: str
    arguments: dict[str, Any] | str = Field(default_factory=dict)

    def get_arguments_dict(self) -> dict[str, Any]:
        """Return parsed arguments dictionary."""
        if isinstance(self.arguments, str):
            try:
                parsed = json.loads(self.arguments)
                if isinstance(parsed, dict):
                    return parsed
                return {"_raw": parsed}
            except Exception:
                return {"_raw": self.arguments}
        return self.arguments


class ToolResult(BaseModel):
    """Output generated from tool execution passed back to the model context."""

    call_id: str
    name: str
    output: str = ""
    error: str | None = None
    exit_code: int = 0

    def to_prompt_message(self) -> PromptMessage:
        """Convert result into a PromptMessage for model history."""
        content = self.output
        if self.error:
            content = f"Error: {self.error}" if not content else f"{content}\nError: {self.error}"
        return PromptMessage(role=MessageRole.TOOL, content=content, name=self.name)
