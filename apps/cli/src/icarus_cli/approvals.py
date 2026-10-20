"""Interactive terminal prompt and safety approval handlers for CLI."""

from __future__ import annotations

from typing import TextIO

from icarus_contracts.tools import ToolCall, ToolDefinition
from icarus_core.agent.approvals import (
    ApprovalEngine,
    ApprovalPolicy,
)
from rich.console import Console

from icarus_cli.ui.approvals import (
    prompt_for_approval,
)


def create_cli_approval_engine(
    auto_approve: bool = False,
    console: Console | None = None,
    stdin: TextIO | None = None,
) -> ApprovalEngine:
    """Create an ApprovalEngine configured with CLI interactive prompts or auto-approve policy."""
    if auto_approve:
        return ApprovalEngine(policy=ApprovalPolicy.AUTO_APPROVE)

    cons = console or Console()

    def _callback(call: ToolCall, definition: ToolDefinition) -> bool:
        return prompt_for_approval(
            tool_call=call,
            tool_definition=definition,
            console=cons,
            stdin=stdin,
        )

    return ApprovalEngine(policy=ApprovalPolicy.INTERACTIVE, prompt_callback=_callback)
