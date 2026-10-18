"""Domain contracts for context budgeting, thresholds, and assembly."""

from __future__ import annotations

from pydantic import BaseModel, Field

from icarus_contracts.provider import PromptMessage


class ContextBudgetConfig(BaseModel):
    """Configuration governing context window sizing, reserves, margins, and compaction triggers."""

    context_window: int = Field(
        default=128000,
        ge=1000,
        description="Total model context window limit in tokens",
    )
    output_reserve: int = Field(
        default=4000,
        ge=100,
        description="Tokens reserved for model completion output",
    )
    safety_margin: int = Field(
        default=2000,
        ge=0,
        description="Safety buffer tokens to prevent hitting provider context ceilings",
    )
    compaction_threshold: float = Field(
        default=0.8,
        ge=0.1,
        le=1.0,
        description="Threshold ratio of input budget at which compaction triggers",
    )

    @property
    def input_budget(self) -> int:
        """Effective budget available for conversation history, system prompt, and tools."""
        return max(0, self.context_window - self.output_reserve - self.safety_margin)

    @property
    def compaction_trigger_tokens(self) -> int:
        """Token threshold above which automated compaction must trigger."""
        return int(self.input_budget * self.compaction_threshold)


class ContextBudgetStatus(BaseModel):
    """Snapshot of current context token consumption against allocated budget."""

    context_window: int
    input_budget: int
    compaction_threshold_tokens: int
    system_tokens: int = 0
    tools_tokens: int = 0
    history_tokens: int = 0
    total_estimated_tokens: int = 0
    remaining_budget: int = 0
    utilization_ratio: float = 0.0
    compaction_needed: bool = False


class CompactionResult(BaseModel):
    """Outcome and telemetry of a conversation history compaction cycle."""

    original_message_count: int
    compacted_message_count: int
    summary_message: PromptMessage
    compacted_messages: list[PromptMessage] = Field(default_factory=list)
    retained_messages: list[PromptMessage] = Field(default_factory=list)
    tokens_before: int = 0
    tokens_after: int = 0
    tokens_saved: int = 0
