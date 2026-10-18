"""Autonomous multi-turn ReAct execution loop for Icarus Agent."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from icarus_contracts.context import CompactionResult
from icarus_contracts.provider import PromptMessage
from icarus_contracts.session import MessageRole
from icarus_contracts.tools import ToolCall, ToolResult

from icarus_core.agent.approvals import ApprovalEngine
from icarus_core.agent.compactor import HistoryCompactor
from icarus_core.agent.context import ContextBudgetManager
from icarus_core.agent.prompts import inject_system_prompt
from icarus_core.providers.base import ModelProvider
from icarus_core.tokens import TokenCounter, get_token_counter
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
    total_tokens: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    compaction_count: int = 0
    model_calls: int = 0
    elapsed_time_seconds: float = 0.0
    budget_counters: dict[str, Any] = field(default_factory=dict)


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

    def on_compaction(self, event: CompactionResult) -> None:
        """Invoked when automated conversation history compaction is executed."""
        ...

    def on_max_tokens(self, max_tokens: int) -> None:
        """Invoked when the loop halts due to reaching the maximum token budget."""
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
        budget_manager: ContextBudgetManager | None = None,
        compactor: HistoryCompactor | None = None,
        max_total_tokens: int | None = None,
        auto_compact: bool = True,
        token_counter: TokenCounter | None = None,
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
        self.max_total_tokens = max_total_tokens
        self.auto_compact = auto_compact
        self.token_counter = (
            token_counter if token_counter is not None else get_token_counter(model=model)
        )
        self.budget_manager = (
            budget_manager
            if budget_manager is not None
            else ContextBudgetManager.from_provider(
                provider=provider, model=model, token_counter=self.token_counter
            )
        )
        self.compactor = (
            compactor
            if compactor is not None
            else HistoryCompactor(token_counter=self.token_counter)
        )

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
        total_prompt_tokens = 0
        total_completion_tokens = 0
        model_calls = 0
        compaction_count = 0
        start_time = time.perf_counter()

        supports_tools = True
        try:
            caps = self.provider.get_capabilities(self.model)
            supports_tools = getattr(caps, "supports_tools", True)
        except Exception:
            supports_tools = True

        tool_schemas: list[dict[str, Any]] | None = None
        if supports_tools and self.tool_registry:
            tool_schemas = self.tool_registry.export_schemas()

        def _make_budget_counters() -> dict[str, Any]:
            total_toks = total_prompt_tokens + total_completion_tokens
            elapsed = round(time.perf_counter() - start_time, 4)
            return {
                "prompt_tokens": total_prompt_tokens,
                "completion_tokens": total_completion_tokens,
                "total_tokens": total_toks,
                "model_calls": model_calls,
                "tool_calls": len(all_tool_calls),
                "compaction_count": compaction_count,
                "elapsed_time_seconds": elapsed,
                "turns": turn_count,
                "compactions": compaction_count,
                "finish_reason": finish_reason,
            }

        try:
            while turn_count < self.max_turns:
                # Check max_total_tokens guardrail before starting turn
                accumulated_tokens = total_prompt_tokens + total_completion_tokens
                if (
                    self.max_total_tokens is not None
                    and accumulated_tokens >= self.max_total_tokens
                ):
                    finish_reason = "max_tokens"
                    final_text = f"Maximum token budget ({self.max_total_tokens}) reached."
                    if observer and hasattr(observer, "on_max_tokens"):
                        observer.on_max_tokens(self.max_total_tokens)
                    _append_message(PromptMessage(role=MessageRole.ASSISTANT, content=final_text))
                    break

                # Context Budget & Pre-flight Compaction
                if self.auto_compact and self.compactor and self.budget_manager:
                    tool_defs = (
                        [t for t in self.tool_registry.list_tools()] if self.tool_registry else None
                    )
                    if self.budget_manager.is_compaction_needed(history, tools=tool_defs):
                        compaction_res = self.compactor.compact(history)
                        if compaction_res.compacted_messages:
                            compaction_count += 1
                            history = [
                                compaction_res.summary_message
                            ] + compaction_res.retained_messages
                            if observer and hasattr(observer, "on_compaction"):
                                observer.on_compaction(compaction_res)

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
                chunk_usage: dict[str, Any] | None = None

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
                    model_calls += 1
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

                        if chunk.usage:
                            chunk_usage = chunk.usage

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
                        total_tokens=total_prompt_tokens + total_completion_tokens,
                        prompt_tokens=total_prompt_tokens,
                        completion_tokens=total_completion_tokens,
                        compaction_count=compaction_count,
                        model_calls=model_calls,
                        elapsed_time_seconds=round(time.perf_counter() - start_time, 4),
                        budget_counters=_make_budget_counters(),
                    )

                accumulated_content = "".join(accumulated_delta)

                # Accumulate token usage for the turn
                if chunk_usage:
                    if isinstance(chunk_usage, dict):
                        turn_prompt_tok = chunk_usage.get("prompt_tokens", 0)
                        turn_comp_tok = chunk_usage.get("completion_tokens", 0)
                    else:
                        turn_prompt_tok = getattr(chunk_usage, "prompt_tokens", 0)
                        turn_comp_tok = getattr(chunk_usage, "completion_tokens", 0)

                    if turn_prompt_tok == 0:
                        turn_prompt_tok = self.token_counter.count_messages(turn_messages)
                    if turn_comp_tok == 0:
                        turn_comp_tok = self.token_counter.count_text(accumulated_content)
                else:
                    turn_prompt_tok = self.token_counter.count_messages(turn_messages)
                    turn_comp_tok = self.token_counter.count_text(accumulated_content)

                total_prompt_tokens += turn_prompt_tok
                total_completion_tokens += turn_comp_tok
                accumulated_tokens = total_prompt_tokens + total_completion_tokens

                # Check max_total_tokens guardrail after completion
                if (
                    self.max_total_tokens is not None
                    and accumulated_tokens >= self.max_total_tokens
                ):
                    finish_reason = "max_tokens"
                    final_text = (
                        accumulated_content
                        or f"Maximum token budget ({self.max_total_tokens}) reached."
                    )
                    _append_message(PromptMessage(role=MessageRole.ASSISTANT, content=final_text))
                    if observer and hasattr(observer, "on_max_tokens"):
                        observer.on_max_tokens(self.max_total_tokens)
                    break

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
                            total_tokens=total_prompt_tokens + total_completion_tokens,
                            prompt_tokens=total_prompt_tokens,
                            completion_tokens=total_completion_tokens,
                            compaction_count=compaction_count,
                            model_calls=model_calls,
                            elapsed_time_seconds=round(time.perf_counter() - start_time, 4),
                            budget_counters=_make_budget_counters(),
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
            total_tokens=total_prompt_tokens + total_completion_tokens,
            prompt_tokens=total_prompt_tokens,
            completion_tokens=total_completion_tokens,
            compaction_count=compaction_count,
            model_calls=model_calls,
            elapsed_time_seconds=round(time.perf_counter() - start_time, 4),
            budget_counters=_make_budget_counters(),
        )
