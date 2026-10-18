"""Token counting engine and provider-aware token estimators."""

from __future__ import annotations

import json
import math
from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import Any

from icarus_contracts.provider import PromptMessage
from icarus_contracts.session import MessageCreate, MessageDTO
from icarus_contracts.tools import ToolCall, ToolDefinition

try:
    import tiktoken
except ImportError:
    tiktoken = None  # type: ignore[assignment]


class TokenCounter(ABC):
    """Abstract interface for calculating token weights across text, messages, and tools."""

    @abstractmethod
    def count_text(self, text: str | None) -> int:
        """Count tokens in a raw string."""

    @abstractmethod
    def count_message(
        self,
        message: PromptMessage | MessageDTO | MessageCreate | dict[str, Any],
    ) -> int:
        """Count tokens in a single structured conversation message."""

    def count_messages(
        self,
        messages: Sequence[PromptMessage | MessageDTO | MessageCreate | dict[str, Any]],
    ) -> int:
        """Count tokens across an entire message history including conversation overhead."""
        if not messages:
            return 0
        return sum(self.count_message(m) for m in messages) + 3

    @abstractmethod
    def count_tool_definition(self, tool: ToolDefinition | dict[str, Any]) -> int:
        """Count tokens occupied by a tool schema definition."""

    def count_tool_definitions(
        self,
        tools: Sequence[ToolDefinition | dict[str, Any]],
    ) -> int:
        """Count tokens occupied by a collection of tool schema definitions."""
        return sum(self.count_tool_definition(t) for t in tools)


def _extract_message_fields(
    msg: PromptMessage | MessageDTO | MessageCreate | dict[str, Any],
) -> tuple[str, str | None, str | None, str | None, list[Any] | None]:
    """Extract (role, content, name, tool_call_id, tool_calls) from diverse message shapes."""
    if isinstance(msg, dict):
        role = str(msg.get("role", "user"))
        content = msg.get("content")
        name = msg.get("name")
        tool_call_id = msg.get("tool_call_id")
        tool_calls = msg.get("tool_calls")
        return role, content, name, tool_call_id, tool_calls

    role = str(getattr(msg, "role", "user"))
    content = getattr(msg, "content", None)
    name = getattr(msg, "name", None)
    tool_call_id = getattr(msg, "tool_call_id", None)
    tool_calls = getattr(msg, "tool_calls", None)
    return role, content, name, tool_call_id, tool_calls


class HeuristicTokenCounter(TokenCounter):
    """Universal offline heuristic token counter (~4 characters per token)."""

    def __init__(
        self,
        chars_per_token: float = 4.0,
        role_overhead: int = 4,
        conversation_overhead: int = 3,
    ) -> None:
        self.chars_per_token = max(1.0, chars_per_token)
        self.role_overhead = role_overhead
        self.conversation_overhead = conversation_overhead

    def count_text(self, text: str | None) -> int:
        if not text:
            return 0
        return max(1, math.ceil(len(text) / self.chars_per_token))

    def count_message(
        self,
        message: PromptMessage | MessageDTO | MessageCreate | dict[str, Any],
    ) -> int:
        role, content, name, tool_call_id, tool_calls = _extract_message_fields(message)

        tokens = self.role_overhead
        if content:
            tokens += self.count_text(str(content))
        if name:
            tokens += self.count_text(str(name)) + 1
        if tool_call_id:
            tokens += self.count_text(str(tool_call_id))

        if tool_calls:
            for tc in tool_calls:
                tokens += 3  # Delimiter overhead
                tc_name = getattr(tc, "name", None) or (
                    tc.get("name") if isinstance(tc, dict) else None
                )
                if tc_name:
                    tokens += self.count_text(str(tc_name))
                tc_args = getattr(tc, "arguments", None) or (
                    tc.get("arguments") if isinstance(tc, dict) else None
                )
                if tc_args:
                    if isinstance(tc_args, dict):
                        tokens += self.count_text(json.dumps(tc_args, separators=(",", ":")))
                    else:
                        tokens += self.count_text(str(tc_args))

        return tokens

    def count_messages(
        self,
        messages: Sequence[PromptMessage | MessageDTO | MessageCreate | dict[str, Any]],
    ) -> int:
        if not messages:
            return 0
        return sum(self.count_message(m) for m in messages) + self.conversation_overhead

    def count_tool_definition(self, tool: ToolDefinition | dict[str, Any]) -> int:
        if hasattr(tool, "to_openai_schema"):
            schema = tool.to_openai_schema()
        elif isinstance(tool, dict):
            schema = tool
        else:
            schema = {"name": getattr(tool, "name", str(tool))}

        json_str = json.dumps(schema, separators=(",", ":"))
        return self.count_text(json_str) + 8


class TiktokenCounter(TokenCounter):
    """Fast, accurate token counter using tiktoken encoding (cl100k_base or o200k_base)."""

    def __init__(
        self,
        model: str | None = None,
        encoding_name: str | None = None,
    ) -> None:
        if tiktoken is None:
            raise ImportError(
                "tiktoken is not available. Install tiktoken or use HeuristicTokenCounter."
            )

        if encoding_name:
            self.encoding_name = encoding_name
        elif model:
            m = model.lower()
            if any(m.startswith(prefix) for prefix in ("gpt-4o", "o1", "o3")):
                self.encoding_name = "o200k_base"
            elif any(m.startswith(prefix) for prefix in ("gpt-4", "gpt-3.5", "grok", "xai/grok")):
                self.encoding_name = "cl100k_base"
            else:
                try:
                    encoding = tiktoken.encoding_for_model(model)
                    self.encoding_name = encoding.name
                except (KeyError, Exception):
                    self.encoding_name = "cl100k_base"
        else:
            self.encoding_name = "cl100k_base"

        self._encoding = tiktoken.get_encoding(self.encoding_name)

    def count_text(self, text: str | None) -> int:
        if not text:
            return 0
        return len(self._encoding.encode(text, disallowed_special=()))

    def count_message(
        self,
        message: PromptMessage | MessageDTO | MessageCreate | dict[str, Any],
    ) -> int:
        role, content, name, tool_call_id, tool_calls = _extract_message_fields(message)

        # Base framing tokens: <|start|>{role}\n{content}<|end|>\n
        tokens = 3
        if role:
            tokens += len(self._encoding.encode(str(role), disallowed_special=()))
        if content:
            tokens += len(self._encoding.encode(str(content), disallowed_special=()))
        if name:
            tokens += 1 + len(self._encoding.encode(str(name), disallowed_special=()))
        if tool_call_id:
            tokens += len(self._encoding.encode(str(tool_call_id), disallowed_special=()))

        if tool_calls:
            for tc in tool_calls:
                tokens += 3  # Syntax framing
                tc_name = getattr(tc, "name", None) or (
                    tc.get("name") if isinstance(tc, dict) else None
                )
                if tc_name:
                    tokens += len(self._encoding.encode(str(tc_name), disallowed_special=()))
                tc_args = getattr(tc, "arguments", None) or (
                    tc.get("arguments") if isinstance(tc, dict) else None
                )
                if tc_args:
                    if isinstance(tc_args, dict):
                        args_str = json.dumps(tc_args, separators=(",", ":"))
                    else:
                        args_str = str(tc_args)
                    tokens += len(self._encoding.encode(args_str, disallowed_special=()))

        return tokens

    def count_messages(
        self,
        messages: Sequence[PromptMessage | MessageDTO | MessageCreate | dict[str, Any]],
    ) -> int:
        if not messages:
            return 0
        return sum(self.count_message(m) for m in messages) + 3

    def count_tool_definition(self, tool: ToolDefinition | dict[str, Any]) -> int:
        if hasattr(tool, "to_openai_schema"):
            schema = tool.to_openai_schema()
        elif isinstance(tool, dict):
            schema = tool
        else:
            schema = {"name": getattr(tool, "name", str(tool))}

        json_str = json.dumps(schema, separators=(",", ":"))
        return len(self._encoding.encode(json_str, disallowed_special=())) + 8


def get_token_counter(
    model: str | None = None,
    encoding_name: str | None = None,
    force_heuristic: bool = False,
) -> TokenCounter:
    """Resolve a suitable token counter, falling back gracefully to heuristic if tiktoken fails."""
    if force_heuristic or tiktoken is None:
        return HeuristicTokenCounter()
    try:
        return TiktokenCounter(model=model, encoding_name=encoding_name)
    except Exception:
        return HeuristicTokenCounter()


def count_tokens(
    target: (
        str
        | PromptMessage
        | MessageDTO
        | MessageCreate
        | ToolDefinition
        | ToolCall
        | Sequence[Any]
        | None
    ),
    model: str | None = None,
    counter: TokenCounter | None = None,
) -> int:
    """Convenience utility to count tokens of strings, messages, tools, or message lists."""
    if target is None:
        return 0

    cnt = counter or get_token_counter(model=model)

    if isinstance(target, str):
        return cnt.count_text(target)

    if hasattr(target, "to_openai_schema"):
        return cnt.count_tool_definition(target)  # ToolDefinition

    if isinstance(target, (PromptMessage, MessageDTO, MessageCreate)):
        return cnt.count_message(target)

    if isinstance(target, ToolCall):
        args_str = (
            json.dumps(target.arguments, separators=(",", ":"))
            if isinstance(target.arguments, dict)
            else str(target.arguments)
        )
        return cnt.count_text(target.name) + cnt.count_text(args_str) + 3

    if isinstance(target, dict):
        if "role" in target:
            return cnt.count_message(target)
        if "name" in target and ("parameters" in target or "description" in target):
            return cnt.count_tool_definition(target)
        return cnt.count_text(json.dumps(target, separators=(",", ":")))

    if isinstance(target, (list, tuple)):
        if not target:
            return 0
        first = target[0]
        if hasattr(first, "to_openai_schema"):
            return cnt.count_tool_definitions(target)
        return cnt.count_messages(target)

    return cnt.count_text(str(target))
