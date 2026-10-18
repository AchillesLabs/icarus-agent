"""Server-Sent Events (SSE) observer for live agent execution telemetry streaming."""

import asyncio
from typing import TYPE_CHECKING

from icarus_contracts import SSEEventPayload
from icarus_contracts.tools import ToolCall, ToolResult

if TYPE_CHECKING:
    from icarus_contracts.context import CompactionResult


class SSEAgentObserver:
    """AgentLoopObserver implementation pushing typed events to an asyncio Queue for SSE."""

    def __init__(self, queue: asyncio.Queue[SSEEventPayload | None], run_id: str) -> None:
        self.queue = queue
        self.run_id = run_id

    def on_token(self, delta: str) -> None:
        """Invoked when model yields an incremental token delta."""
        if delta:
            self.queue.put_nowait(SSEEventPayload.token(delta=delta, run_id=self.run_id))

    def on_turn_start(self, turn: int) -> None:
        """Invoked at the beginning of an agent reasoning/execution turn."""
        if turn > 1:
            self.queue.put_nowait(SSEEventPayload.turn_start(turn=turn, run_id=self.run_id))

    def on_turn_end(self, turn: int) -> None:
        """Invoked at the completion of an agent turn."""
        pass

    def on_tool_start(self, tool_call: ToolCall) -> None:
        """Invoked when a tool begins evaluation."""
        self.queue.put_nowait(
            SSEEventPayload.tool_start(
                tool_name=tool_call.name,
                arguments=tool_call.get_arguments_dict(),
                tool_call_id=tool_call.id,
                run_id=self.run_id,
            )
        )

    def on_tool_end(self, tool_result: ToolResult) -> None:
        """Invoked when tool execution concludes."""
        self.queue.put_nowait(
            SSEEventPayload.tool_end(
                tool_name=tool_result.name,
                output=tool_result.output,
                error=tool_result.error,
                tool_call_id=tool_result.call_id,
                run_id=self.run_id,
            )
        )

    def on_compaction(self, event: "CompactionResult") -> None:
        """Invoked when context compaction is triggered."""
        self.queue.put_nowait(
            SSEEventPayload.compaction(
                tokens_saved=event.tokens_saved,
                original_message_count=event.original_message_count,
                compacted_message_count=event.compacted_message_count,
                run_id=self.run_id,
            )
        )

    def on_max_turns(self, max_turns: int) -> None:
        """Invoked when max turn budget is reached."""
        pass

    def on_max_tokens(self, max_tokens: int) -> None:
        """Invoked when max token budget is reached."""
        pass
