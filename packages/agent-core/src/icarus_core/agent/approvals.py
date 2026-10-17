"""Approval policy engine and human-in-the-loop decision evaluation."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from icarus_contracts.tools import (
    ToolCall,
    ToolDefinition,
    ToolResult,
    ToolSafetyCategory,
)

from icarus_core.tools.base import BaseTool


class ApprovalPolicy(StrEnum):
    """Execution policy for tools requiring confirmation."""

    INTERACTIVE = "interactive"
    AUTO_APPROVE = "auto_approve"
    DENY = "deny"


@dataclass
class ApprovalDecision:
    """Outcome of evaluating an approval policy for a tool execution."""

    approved: bool
    reason: str | None = None


ApprovalPromptCallback = Callable[[ToolCall, ToolDefinition], bool]


class ApprovalEngine:
    """Policy engine guarding destructive operations and requesting user confirmation."""

    def __init__(
        self,
        policy: ApprovalPolicy | str = ApprovalPolicy.INTERACTIVE,
        prompt_callback: ApprovalPromptCallback | None = None,
    ) -> None:
        if isinstance(policy, str):
            policy = ApprovalPolicy(policy.lower())
        self.policy = policy
        self.prompt_callback = prompt_callback

    def requires_approval(self, tool_definition: ToolDefinition) -> bool:
        """Check whether a tool's safety category necessitates approval."""
        return tool_definition.safety_category == ToolSafetyCategory.REQUIRES_APPROVAL

    def evaluate(
        self,
        tool_call: ToolCall,
        tool_definition: ToolDefinition,
    ) -> ApprovalDecision:
        """Evaluate approval status under the active policy."""
        if not self.requires_approval(tool_definition):
            return ApprovalDecision(approved=True)

        if self.policy == ApprovalPolicy.AUTO_APPROVE:
            return ApprovalDecision(approved=True, reason="Auto-approved by policy.")

        if self.policy == ApprovalPolicy.DENY:
            return ApprovalDecision(
                approved=False,
                reason="Execution denied by approval policy: DENY.",
            )

        if self.policy == ApprovalPolicy.INTERACTIVE:
            if self.prompt_callback is None:
                return ApprovalDecision(
                    approved=False,
                    reason=(
                        "Execution denied: no approval prompt callback configured "
                        "for interactive policy."
                    ),
                )
            try:
                approved = bool(self.prompt_callback(tool_call, tool_definition))
            except Exception as exc:
                return ApprovalDecision(
                    approved=False,
                    reason=f"Interactive approval prompt raised error: {exc}",
                )

            if approved:
                return ApprovalDecision(approved=True, reason="Approved by user.")
            return ApprovalDecision(approved=False, reason="Action rejected by user.")

        return ApprovalDecision(approved=False, reason="Unknown approval policy.")

    def create_rejection_result(
        self,
        tool_call: ToolCall,
        reason: str = "Action rejected by user.",
    ) -> ToolResult:
        """Construct a non-crashing ToolResult reflecting the rejection."""
        return ToolResult(
            call_id=tool_call.id,
            name=tool_call.name,
            output="",
            error=reason,
            exit_code=1,
        )

    def execute_with_approval(
        self,
        tool_call: ToolCall,
        tool: BaseTool,
        workspace_root: Path | str,
    ) -> ToolResult:
        """Evaluate approval policy and execute tool if approved, or return clean rejection."""
        decision = self.evaluate(tool_call, tool.definition)
        if decision.approved:
            args = tool_call.get_arguments_dict()
            return tool.execute(
                arguments=args,
                workspace_root=workspace_root,
                call_id=tool_call.id,
            )
        return self.create_rejection_result(
            tool_call=tool_call,
            reason=decision.reason or "Action rejected by user.",
        )
