"""Agent orchestration, prompts, approvals, and execution loops."""

from icarus_core.agent.approvals import (
    ApprovalDecision,
    ApprovalEngine,
    ApprovalPolicy,
    ApprovalPromptCallback,
)
from icarus_core.agent.compactor import (
    HistoryCompactor,
    reconstruct_session_prompt_history,
)
from icarus_core.agent.context import ContextBudgetManager
from icarus_core.agent.loop import (
    AgentLoop,
    AgentLoopObserver,
    AgentLoopResult,
)
from icarus_core.agent.prompts import (
    SystemPromptBuilder,
    build_system_prompt,
    inject_system_prompt,
)

__all__ = [
    "AgentLoop",
    "AgentLoopObserver",
    "AgentLoopResult",
    "ApprovalDecision",
    "ApprovalEngine",
    "ApprovalPolicy",
    "ApprovalPromptCallback",
    "ContextBudgetManager",
    "HistoryCompactor",
    "SystemPromptBuilder",
    "build_system_prompt",
    "inject_system_prompt",
    "reconstruct_session_prompt_history",
]
