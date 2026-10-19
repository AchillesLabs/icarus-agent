"""Server-Sent Events (SSE) observer for live agent execution telemetry streaming."""

import asyncio
from typing import TYPE_CHECKING

from icarus_contracts import SSEEventPayload
from icarus_contracts.tools import ToolCall, ToolResult
from icarus_core.security import redact_secret

if TYPE_CHECKING:
    from icarus_contracts.context import CompactionResult


class SSEAgentObserver:
    """AgentLoopObserver implementation pushing typed events to an asyncio Queue for SSE."""

    def __init__(
        self,
        queue: asyncio.Queue[SSEEventPayload | None],
        run_id: str,
        secret_to_redact: str | None = None,
    ) -> None:
        self.queue = queue
        self.run_id = run_id
        self.secret_to_redact = secret_to_redact

    def on_token(self, delta: str) -> None:
        """Invoked when model yields an incremental token delta."""
        if delta:
            safe_delta = redact_secret(delta, self.secret_to_redact)
            self.queue.put_nowait(SSEEventPayload.token(delta=safe_delta, run_id=self.run_id))

    def on_turn_start(self, turn: int) -> None:
        """Invoked at the beginning of an agent reasoning/execution turn."""
        if turn > 1:
            self.queue.put_nowait(SSEEventPayload.turn_start(turn=turn, run_id=self.run_id))

    def on_turn_end(self, turn: int) -> None:
        """Invoked at the completion of an agent turn."""
        pass

    def on_tool_start(self, tool_call: ToolCall) -> None:
        """Invoked when a tool begins evaluation."""
        safe_args = redact_secret(tool_call.get_arguments_dict(), self.secret_to_redact)
        self.queue.put_nowait(
            SSEEventPayload.tool_start(
                tool_name=tool_call.name,
                arguments=safe_args,
                tool_call_id=tool_call.id,
                run_id=self.run_id,
            )
        )

    def on_tool_end(self, tool_result: ToolResult) -> None:
        """Invoked when tool execution concludes."""
        safe_output = redact_secret(tool_result.output, self.secret_to_redact)
        safe_error = redact_secret(tool_result.error, self.secret_to_redact)
        self.queue.put_nowait(
            SSEEventPayload.tool_end(
                tool_name=tool_result.name,
                output=safe_output,
                error=safe_error,
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
