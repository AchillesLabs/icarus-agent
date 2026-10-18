"""Provider utility functions for message formatting and streaming tool call accumulation."""

from __future__ import annotations

import json
from typing import Any

from icarus_contracts.provider import PromptMessage
from icarus_contracts.tools import ToolCall


def format_chat_messages(messages: list[PromptMessage]) -> list[dict[str, Any]]:
    """Format PromptMessage instances into OpenAI-compatible message dicts.

    Preserves assistant tool_calls and tool-role tool_call_id fields.
    """
    formatted: list[dict[str, Any]] = []
    for m in messages:
        role_str = m.role.value if hasattr(m.role, "value") else str(m.role)
        item: dict[str, Any] = {"role": role_str, "content": m.content}
        if m.name:
            item["name"] = m.name
        if m.tool_call_id:
            item["tool_call_id"] = m.tool_call_id
        if m.tool_calls:
            item["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.name,
                        "arguments": json.dumps(tc.get_arguments_dict())
                        if isinstance(tc.arguments, dict)
                        else str(tc.arguments),
                    },
                }
                for tc in m.tool_calls
            ]
        formatted.append(item)
    return formatted


def parse_response_tool_calls(raw_tool_calls: list[dict[str, Any]] | None) -> list[ToolCall]:
    """Parse raw OpenAI tool call objects from non-streaming response into ToolCall models."""
    if not raw_tool_calls:
        return []
    parsed: list[ToolCall] = []
    for tc in raw_tool_calls:
        func = tc.get("function", {})
        parsed.append(
            ToolCall(
                id=tc.get("id", "call_default"),
                name=func.get("name", ""),
                arguments=func.get("arguments", "{}"),
            )
        )
    return parsed


class ToolCallAccumulator:
    """Accumulates chunked SSE tool_calls deltas into complete ToolCall objects."""

    def __init__(self) -> None:
        self._calls: dict[int, dict[str, Any]] = {}

    def update(self, deltas: list[dict[str, Any]]) -> None:
        """Merge tool call delta pieces into indexed accumulator."""
        for delta in deltas:
            idx = delta.get("index", 0)
            if idx not in self._calls:
                func = delta.get("function", {})
                self._calls[idx] = {
                    "id": delta.get("id", ""),
                    "name": func.get("name", "") if func else "",
                    "arguments": func.get("arguments", "") if func else "",
                }
            else:
                if delta.get("id"):
                    self._calls[idx]["id"] += delta["id"]
                func = delta.get("function", {})
                if func and func.get("name"):
                    self._calls[idx]["name"] += func["name"]
                if func and func.get("arguments"):
                    self._calls[idx]["arguments"] += func["arguments"]

    def get_tool_calls(self) -> list[ToolCall]:
        """Return assembled ToolCall models for all accumulated tool calls."""
        results: list[ToolCall] = []
        for idx in sorted(self._calls.keys()):
            call_data = self._calls[idx]
            results.append(
                ToolCall(
                    id=call_data["id"] or f"call_{idx}",
                    name=call_data["name"],
                    arguments=call_data["arguments"],
                )
            )
        return results
