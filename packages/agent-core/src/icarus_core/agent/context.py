"""Context budget manager and context hierarchy prompt assembly."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from icarus_contracts.context import ContextBudgetConfig, ContextBudgetStatus
from icarus_contracts.provider import PromptMessage
from icarus_contracts.session import MessageRole
from icarus_contracts.tools import ToolDefinition

from icarus_core.tokens import TokenCounter, get_token_counter


class ContextBudgetManager:
    """Manages context token allocation, threshold triggers, and prioritized prompt assembly."""

    def __init__(
        self,
        config: ContextBudgetConfig | None = None,
        token_counter: TokenCounter | None = None,
        model: str | None = None,
        context_window: int | None = None,
    ) -> None:
        self.config = config if config is not None else ContextBudgetConfig()
        if context_window is not None:
            self.config.context_window = context_window
        self.model = model
        self.token_counter = (
            token_counter if token_counter is not None else get_token_counter(model=model)
        )

    @classmethod
    def from_provider(
        cls,
        provider: Any,
        model: str | None = None,
        output_reserve: int | None = None,
        safety_margin: int | None = None,
        compaction_threshold: float | None = None,
        token_counter: TokenCounter | None = None,
    ) -> ContextBudgetManager:
        """Construct a ContextBudgetManager dynamic to a provider's advertised capabilities."""
        context_window = 128000
        try:
            caps = provider.get_capabilities(model)
            if hasattr(caps, "max_context_tokens") and caps.max_context_tokens:
                context_window = caps.max_context_tokens
        except Exception:
            context_window = 128000

        cfg = ContextBudgetConfig(
            context_window=context_window,
            output_reserve=output_reserve if output_reserve is not None else 4000,
            safety_margin=safety_margin if safety_margin is not None else 2000,
            compaction_threshold=compaction_threshold if compaction_threshold is not None else 0.8,
        )
        return cls(config=cfg, model=model, token_counter=token_counter)

    def calculate_input_budget(self, context_window: int | None = None) -> int:
        """Compute the input budget: max(0, context_window - output_reserve - safety_margin)."""
        window = context_window if context_window is not None else self.config.context_window
        return max(0, window - self.config.output_reserve - self.config.safety_margin)

    def is_compaction_needed(
        self,
        messages: Sequence[PromptMessage | dict[str, Any]],
        tools: Sequence[ToolDefinition | dict[str, Any]] | None = None,
    ) -> bool:
        """Check if message and tool tokens reach or exceed the compaction trigger threshold."""
        status = self.get_budget_status(messages=messages, tools=tools)
        return status.compaction_needed

    def get_budget_status(
        self,
        messages: Sequence[PromptMessage | dict[str, Any]],
        tools: Sequence[ToolDefinition | dict[str, Any]] | None = None,
    ) -> ContextBudgetStatus:
        """Compute a detailed status snapshot of current token consumption and budget headrooms."""
        input_budget = self.calculate_input_budget()
        trigger_tokens = int(input_budget * self.config.compaction_threshold)

        system_tokens = 0
        history_tokens = 0
        for m in messages:
            role = m.get("role") if isinstance(m, dict) else getattr(m, "role", None)
            role_val = role.value if hasattr(role, "value") else str(role)
            tokens = self.token_counter.count_message(m)
            if role_val == MessageRole.SYSTEM.value:
                system_tokens += tokens
            else:
                history_tokens += tokens

        tools_tokens = 0
        if tools:
            tools_tokens = self.token_counter.count_tool_definitions(tools)

        total_tokens = system_tokens + history_tokens + tools_tokens
        if messages:
            total_tokens += 3

        remaining = max(0, input_budget - total_tokens)
        utilization = min(1.0, total_tokens / max(1, input_budget)) if input_budget > 0 else 1.0
        compaction_needed = total_tokens >= trigger_tokens and input_budget > 0

        return ContextBudgetStatus(
            context_window=self.config.context_window,
            input_budget=input_budget,
            compaction_threshold_tokens=trigger_tokens,
            system_tokens=system_tokens,
            tools_tokens=tools_tokens,
            history_tokens=history_tokens,
            total_estimated_tokens=total_tokens,
            remaining_budget=remaining,
            utilization_ratio=round(utilization, 4),
            compaction_needed=compaction_needed,
        )

    def assemble_prompt(
        self,
        system_prompt: str | PromptMessage | None = None,
        task_constraints: str | None = None,
        compaction_summary: str | PromptMessage | None = None,
        history_messages: Sequence[PromptMessage] = (),
        tools: Sequence[ToolDefinition | dict[str, Any]] | None = None,
    ) -> list[PromptMessage]:
        """Assemble messages strictly adhering to the context hierarchy:

        1. System persona and safety instructions (never evicted)
        2. Current user task goals and constraints
        3. Compaction summary of older history (if present)
        4. Recent conversation turns (retained verbatim)
        """
        assembled: list[PromptMessage] = []

        # 1. System Persona & Safety Rules
        if system_prompt is not None:
            if isinstance(system_prompt, PromptMessage):
                assembled.append(system_prompt)
            elif isinstance(system_prompt, str) and system_prompt.strip():
                assembled.append(PromptMessage(role=MessageRole.SYSTEM, content=system_prompt))
        else:
            # Preserve leading system message in history if no explicit prompt given
            if history_messages and (
                history_messages[0].role == MessageRole.SYSTEM
                or getattr(history_messages[0].role, "value", None) == MessageRole.SYSTEM.value
            ):
                assembled.append(history_messages[0])
                history_messages = history_messages[1:]

        # 2. Task constraints / instructions
        if task_constraints and task_constraints.strip():
            assembled.append(
                PromptMessage(
                    role=MessageRole.SYSTEM,
                    content=f"## [Task Constraints]\n{task_constraints.strip()}",
                )
            )

        # 3. Compaction summary (if present)
        if compaction_summary is not None:
            if isinstance(compaction_summary, PromptMessage):
                assembled.append(compaction_summary)
            elif isinstance(compaction_summary, str) and compaction_summary.strip():
                assembled.append(
                    PromptMessage(
                        role=MessageRole.SYSTEM,
                        content=f"## [Previous Conversation Summary]\n{compaction_summary.strip()}",
                    )
                )

        # 4. Recent conversation turns (retained verbatim)
        for msg in history_messages:
            if (
                (
                    msg.role == MessageRole.SYSTEM
                    or getattr(msg.role, "value", None) == MessageRole.SYSTEM.value
                )
                and len(assembled) > 0
                and msg.content == assembled[0].content
            ):
                continue
            assembled.append(msg)

        return assembled
