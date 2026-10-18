"""Autonomous multi-turn ReAct execution loop for Icarus Agent."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from icarus_contracts.provider import PromptMessage
from icarus_contracts.session import MessageRole
from icarus_contracts.tools import ToolCall, ToolResult

from icarus_core.agent.approvals import ApprovalEngine
from icarus_core.agent.prompts import inject_system_prompt
from icarus_core.providers.base import ModelProvider
from icarus_core.tools.registry import ToolRegistry, create_default_registry


@dataclass
class AgentLoopResult:
    """Outcome and complete conversation history of an autonomous agent run."""

    content: str
    messages: list[PromptMessage] = field(default_factory=list)
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_results: list[ToolResult] = field(default_factory=list)
    total_turns: int = 0
    finish_reason: str = "stop"


@runtime_checkable
class AgentLoopObserver(Protocol):
    """Protocol for receiving streaming tokens and tool execution lifecycle notifications."""

    def on_token(self, delta: str) -> None:
        """Invoked when an incremental token delta is yielded by the model."""
        ...

    def on_tool_start(self, tool_call: ToolCall) -> None:
        """Invoked before a tool begins evaluation and execution."""
        ...

    def on_tool_end(self, tool_result: ToolResult) -> None:
        """Invoked immediately after tool execution concludes with an outcome."""
        ...

    def on_turn_start(self, turn: int) -> None:
        """Invoked at the beginning of an agent reasoning/execution turn."""
        ...

    def on_turn_end(self, turn: int) -> None:
        """Invoked at the completion of an agent turn."""
        ...

    def on_max_turns(self, max_turns: int) -> None:
        """Invoked when the loop halts due to reaching the maximum turn budget."""
        ...


class AgentLoop:
    """Autonomous ReAct state engine managing cycles between LLM reasoning and tool dispatch."""

    def __init__(
        self,
        provider: ModelProvider,
        tool_registry: ToolRegistry | None = None,
        approval_engine: ApprovalEngine | None = None,
        workspace_root: Path | str | None = None,
        max_turns: int = 25,
        model: str | None = None,
        temperature: float = 0.7,
        inject_system: bool = True,
        message_callback: Callable[[PromptMessage], None] | None = None,
    ) -> None:
        self.provider = provider
        self.tool_registry = (
            tool_registry if tool_registry is not None else create_default_registry()
        )
        self.approval_engine = approval_engine if approval_engine is not None else ApprovalEngine()
        self.workspace_root = Path(workspace_root) if workspace_root is not None else Path.cwd()
        self.max_turns = max_turns
        self.model = model
        self.temperature = temperature
        self.inject_system = inject_system
        self.message_callback = message_callback

    async def run(
        self,
        prompt: str | None = None,
        messages: list[PromptMessage] | None = None,
        observer: AgentLoopObserver | None = None,
        message_callback: Callable[[PromptMessage], None] | None = None,
    ) -> AgentLoopResult:
        """Execute the multi-turn ReAct reasoning and tool dispatch cycle until completion."""
        effective_callback = message_callback or self.message_callback

        def _append_message(msg: PromptMessage) -> None:
            history.append(msg)
            if effective_callback:
                effective_callback(msg)

        history: list[PromptMessage] = list(messages) if messages is not None else []
        if prompt is not None:
            history.append(PromptMessage(role=MessageRole.USER, content=prompt))

        all_tool_calls: list[ToolCall] = []
        all_tool_results: list[ToolResult] = []
        turn_count = 0
        final_text = ""
        finish_reason = "stop"

        supports_tools = True
        try:
            caps = self.provider.get_capabilities(self.model)
            supports_tools = getattr(caps, "supports_tools", True)
        except Exception:
            supports_tools = True

        tool_schemas: list[dict[str, Any]] | None = None
        if supports_tools and self.tool_registry:
            tool_schemas = self.tool_registry.export_schemas()

        try:
            while turn_count < self.max_turns:
                turn_count += 1
                if observer and hasattr(observer, "on_turn_start"):
                    observer.on_turn_start(turn_count)

                # Prepare messages with system instruction if enabled
                if self.inject_system:
                    tool_names = (
                        [t.name for t in self.tool_registry.list_tools()]
                        if self.tool_registry
                        else None
                    )
                    turn_messages = inject_system_prompt(
                        history,
                        cwd=self.workspace_root,
                        available_tools=tool_names,
                    )
                else:
                    turn_messages = list(history)

                accumulated_delta: list[str] = []
                turn_tool_calls: list[ToolCall] = []

                stream_kwargs: dict[str, Any] = {
                    "model": self.model,
                    "temperature": self.temperature,
                }
                if tool_schemas:
                    try:
                        import inspect

                        sig = inspect.signature(self.provider.stream)
                        if "tools" in sig.parameters or any(
                            p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()
                        ):
                            stream_kwargs["tools"] = tool_schemas
                    except Exception:
                        stream_kwargs["tools"] = tool_schemas

                try:
                    async for chunk in self.provider.stream(
                        messages=turn_messages,
                        **stream_kwargs,
                    ):
                        if chunk.delta:
                            accumulated_delta.append(chunk.delta)
                            if observer and hasattr(observer, "on_token"):
                                observer.on_token(chunk.delta)

                        if chunk.tool_calls:
                            turn_tool_calls.extend(chunk.tool_calls)

                        if chunk.finish_reason:
                            finish_reason = chunk.finish_reason
                except (KeyboardInterrupt, asyncio.CancelledError):
                    accumulated_content = "".join(accumulated_delta)
                    final_text = (
                        f"{accumulated_content}\n[Execution interrupted by user]"
                        if accumulated_content
                        else "[Execution interrupted by user]"
                    )
                    finish_reason = "cancelled"
                    _append_message(PromptMessage(role=MessageRole.ASSISTANT, content=final_text))
                    return AgentLoopResult(
                        content=final_text,
                        messages=history,
                        tool_calls=all_tool_calls,
                        tool_results=all_tool_results,
                        total_turns=turn_count,
                        finish_reason=finish_reason,
                    )

                accumulated_content = "".join(accumulated_delta)

                # If the model produced no tool calls, it has finished with a final user response
                if not turn_tool_calls:
                    final_text = accumulated_content
                    _append_message(PromptMessage(role=MessageRole.ASSISTANT, content=final_text))
                    if observer and hasattr(observer, "on_turn_end"):
                        observer.on_turn_end(turn_count)
                    break

                # Model decided to invoke one or more tools
                assistant_content = accumulated_content if accumulated_content else None
                _append_message(
                    PromptMessage(
                        role=MessageRole.ASSISTANT,
                        content=assistant_content,
                        tool_calls=turn_tool_calls,
                    )
                )

                # Execute requested tools in sequence
                for i, tc in enumerate(turn_tool_calls):
                    all_tool_calls.append(tc)
                    if observer and hasattr(observer, "on_tool_start"):
                        observer.on_tool_start(tc)

                    try:
                        tool_inst = self.tool_registry.get(tc.name)
                        if tool_inst is None:
                            res = ToolResult(
                                call_id=tc.id,
                                name=tc.name,
                                output="",
                                error=f"Tool '{tc.name}' not found in registry.",
                                exit_code=1,
                            )
                        else:
                            res = self.approval_engine.execute_with_approval(
                                tool_call=tc,
                                tool=tool_inst,
                                workspace_root=self.workspace_root,
                            )
                    except (KeyboardInterrupt, asyncio.CancelledError):
                        res = ToolResult(
                            call_id=tc.id,
                            name=tc.name,
                            output="",
                            error="Tool execution cancelled by user (SIGINT).",
                            exit_code=130,
                        )
                        all_tool_results.append(res)
                        if observer and hasattr(observer, "on_tool_end"):
                            observer.on_tool_end(res)
                        _append_message(res.to_prompt_message())

                        # Skip remaining tool calls with cancellation result so
                        # every call has a matching response
                        for rem_tc in turn_tool_calls[i + 1 :]:
                            all_tool_calls.append(rem_tc)
                            rem_res = ToolResult(
                                call_id=rem_tc.id,
                                name=rem_tc.name,
                                output="",
                                error="Tool execution skipped due to user cancellation.",
                                exit_code=130,
                            )
                            all_tool_results.append(rem_res)
                            _append_message(rem_res.to_prompt_message())

                        finish_reason = "cancelled"
                        final_text = "[Execution cancelled by user]"
                        _append_message(
                            PromptMessage(role=MessageRole.ASSISTANT, content=final_text)
                        )
                        return AgentLoopResult(
                            content=final_text,
                            messages=history,
                            tool_calls=all_tool_calls,
                            tool_results=all_tool_results,
                            total_turns=turn_count,
                            finish_reason=finish_reason,
                        )

                    all_tool_results.append(res)
                    if observer and hasattr(observer, "on_tool_end"):
                        observer.on_tool_end(res)

                    _append_message(res.to_prompt_message())

                if observer and hasattr(observer, "on_turn_end"):
                    observer.on_turn_end(turn_count)

            if turn_count >= self.max_turns and not final_text:
                final_text = f"Maximum turn budget ({self.max_turns}) reached."
                finish_reason = "max_turns"
                if observer and hasattr(observer, "on_max_turns"):
                    observer.on_max_turns(self.max_turns)
                _append_message(PromptMessage(role=MessageRole.ASSISTANT, content=final_text))

        except (KeyboardInterrupt, asyncio.CancelledError):
            finish_reason = "cancelled"
            if not final_text:
                final_text = "[Execution cancelled by user]"
                _append_message(PromptMessage(role=MessageRole.ASSISTANT, content=final_text))

        return AgentLoopResult(
            content=final_text,
            messages=history,
            tool_calls=all_tool_calls,
            tool_results=all_tool_results,
            total_turns=turn_count,
            finish_reason=finish_reason,
        )
