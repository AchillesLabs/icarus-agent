"""Turn-boundary conversation history compactor with tool-pairing protection."""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

from icarus_contracts.context import CompactionResult
from icarus_contracts.provider import PromptMessage
from icarus_contracts.session import MessageRole

from icarus_core.tokens import TokenCounter, get_token_counter


class HistoryCompactor:
    """Intelligent conversation history compactor preserving function-calling invariants."""

    def __init__(
        self,
        token_counter: TokenCounter | None = None,
        min_retained_turns: int = 2,
    ) -> None:
        self.token_counter = token_counter if token_counter is not None else get_token_counter()
        self.min_retained_turns = max(1, min_retained_turns)

    def _get_atomic_tool_groups(self, messages: Sequence[PromptMessage]) -> list[tuple[int, int]]:
        """Identify [start_idx, end_idx] for assistant tool calls and matching tool results."""
        groups: list[tuple[int, int]] = []
        i = 0
        n = len(messages)
        while i < n:
            msg = messages[i]
            if (
                msg.role == MessageRole.ASSISTANT
                or getattr(msg.role, "value", None) == MessageRole.ASSISTANT.value
            ) and msg.tool_calls:
                start = i
                end = i
                # Track subsequent tool results matching these calls
                j = i + 1
                while j < n:
                    next_msg = messages[j]
                    if (
                        next_msg.role == MessageRole.TOOL
                        or getattr(next_msg.role, "value", None) == MessageRole.TOOL.value
                    ):
                        end = j
                        j += 1
                    else:
                        break
                groups.append((start, end))
                i = end + 1
            else:
                i += 1
        return groups

    def find_safe_cut_index(
        self,
        messages: Sequence[PromptMessage],
        target_retained_count: int | None = None,
    ) -> int:
        """Find a clean cut index that preserves tool call pairing and message validity."""
        n = len(messages)
        if n <= 1:
            return 0

        target_retained = (
            target_retained_count
            if target_retained_count is not None
            else self.min_retained_turns * 2
        )
        raw_cut = max(0, min(n, n - target_retained))

        tool_groups = self._get_atomic_tool_groups(messages)

        # Check if raw_cut falls strictly inside an atomic tool group
        safe_cut = raw_cut
        for start, end in tool_groups:
            # If cut falls between start and end+1 (i.e. start < cut <= end), it splits the group
            if start < safe_cut <= end:
                # Adjust cut to keep the entire tool turn in retained messages
                safe_cut = start if start > 0 else end + 1
                break

        # Invariant check: Retained history must NEVER start with an orphaned Tool message
        while safe_cut < n:
            role = messages[safe_cut].role
            role_val = role.value if hasattr(role, "value") else str(role)
            if role_val == MessageRole.TOOL.value:
                # Find the assistant message that spawned this tool or advance past it
                found_parent = False
                for start, end in tool_groups:
                    if start <= safe_cut <= end:
                        safe_cut = start
                        found_parent = True
                        break
                if not found_parent or safe_cut == 0:
                    safe_cut += 1
            else:
                break

        return min(n, max(0, safe_cut))

    def partition_history(
        self,
        messages: Sequence[PromptMessage],
        target_retained_turns: int | None = None,
    ) -> tuple[list[PromptMessage], list[PromptMessage]]:
        """Partition history into compaction candidates and retained verbatim messages."""
        target_retained = (
            target_retained_turns * 2
            if target_retained_turns is not None
            else self.min_retained_turns * 2
        )
        cut = self.find_safe_cut_index(messages, target_retained_count=target_retained)
        return list(messages[:cut]), list(messages[cut:])

    def extract_summary_details(
        self, compacted_messages: Sequence[PromptMessage]
    ) -> dict[str, Any]:
        """Extract structured domain information from compacted messages."""
        task_goal = "Not explicitly stated"
        decisions: list[str] = []
        touched_files: list[str] = []
        commands: list[str] = []
        tool_findings: list[str] = []

        for msg in compacted_messages:
            role = msg.role.value if hasattr(msg.role, "value") else str(msg.role)
            content = (msg.content or "").strip()

            # First user prompt captures the initial goal
            if role == MessageRole.USER.value and task_goal == "Not explicitly stated":
                first_line = content.split("\n")[0].strip()
                task_goal = first_line if len(first_line) <= 300 else first_line[:300] + "..."

            # Assistant messages record decisions and answers
            elif role == MessageRole.ASSISTANT.value and content:
                # Capture concise decision summaries
                first_line = content.split("\n")[0].strip()
                if first_line and first_line not in decisions:
                    decisions.append(first_line)

            # Inspect tool calls for file paths and shell commands
            if msg.tool_calls:
                for tc in msg.tool_calls:
                    args = tc.arguments
                    if isinstance(args, str):
                        try:
                            args = json.loads(args)
                        except Exception:
                            args = {}

                    if isinstance(args, dict):
                        for k, v in args.items():
                            if k in ("path", "filepath", "file_path", "target_file") and v:
                                if str(v) not in touched_files:
                                    touched_files.append(str(v))
                            elif k in ("command", "cmd") and v and str(v) not in commands:
                                commands.append(str(v))

            # Tool results capture outputs and exit codes
            elif role == MessageRole.TOOL.value and content:
                snippet = content[:120].replace("\n", " ").strip()
                name = msg.name or "tool"
                tool_findings.append(f"{name}: {snippet}")

        return {
            "task_goal": task_goal,
            "decisions": decisions,
            "touched_files": touched_files,
            "commands": commands,
            "tool_findings": tool_findings,
        }

    def format_summary(self, compacted_messages: Sequence[PromptMessage]) -> str:
        """Render a structured markdown summary retaining critical technical context."""
        details = self.extract_summary_details(compacted_messages)

        lines: list[str] = [
            "## [Previous Conversation Summary]",
            "",
            "### Original Task Goal",
            details["task_goal"],
            "",
            "### Key Decisions & Actions",
        ]

        if details["decisions"]:
            for d in details["decisions"][:5]:
                lines.append(f"- {d}")
        else:
            lines.append("- Multi-turn execution and environment inspection.")

        lines.extend(["", "### Touched Files & Commands"])
        if details["touched_files"]:
            lines.append(f"- Files: {', '.join(details['touched_files'])}")
        if details["commands"]:
            lines.append(f"- Commands: {', '.join(details['commands'])}")
        if not details["touched_files"] and not details["commands"]:
            lines.append("- None recorded.")

        lines.extend(["", "### Key Tool Results"])
        if details["tool_findings"]:
            for f in details["tool_findings"][:5]:
                lines.append(f"- {f}")
        else:
            lines.append("- All prior tool executions completed successfully.")

        lines.extend(
            [
                "",
                "### Pending Next Steps",
                "- Continue execution following active user instructions.",
            ]
        )

        return "\n".join(lines)

    def compact(
        self,
        messages: Sequence[PromptMessage],
        target_retained_turns: int | None = None,
        keep_recent_count: int | None = None,
    ) -> CompactionResult:
        """Execute history compaction and return structured result with token metrics."""
        msg_list = list(messages)
        n = len(msg_list)

        # Skip compaction if history does not have enough turns
        min_msgs = self.min_retained_turns * 2
        if n <= min_msgs:
            dummy_summary = PromptMessage(
                role=MessageRole.SYSTEM,
                content="## [Previous Conversation Summary]\nNo compaction.",
            )
            tokens = self.token_counter.count_messages(msg_list)
            return CompactionResult(
                original_message_count=n,
                compacted_message_count=n,
                summary_message=dummy_summary,
                compacted_messages=[],
                retained_messages=msg_list,
                tokens_before=tokens,
                tokens_after=tokens,
                tokens_saved=0,
            )

        target_retained = (
            keep_recent_count
            if keep_recent_count is not None
            else (
                target_retained_turns * 2
                if target_retained_turns is not None
                else self.min_retained_turns * 2
            )
        )

        cut = self.find_safe_cut_index(msg_list, target_retained_count=target_retained)
        compacted = msg_list[:cut]
        retained = msg_list[cut:]

        if not compacted:
            dummy_summary = PromptMessage(
                role=MessageRole.SYSTEM,
                content="## [Previous Conversation Summary]\nNo compaction.",
            )
            tokens = self.token_counter.count_messages(msg_list)
            return CompactionResult(
                original_message_count=n,
                compacted_message_count=n,
                summary_message=dummy_summary,
                compacted_messages=[],
                retained_messages=msg_list,
                tokens_before=tokens,
                tokens_after=tokens,
                tokens_saved=0,
            )

        summary_text = self.format_summary(compacted)
        summary_message = PromptMessage(role=MessageRole.SYSTEM, content=summary_text)

        tokens_before = self.token_counter.count_messages(msg_list)
        reconstructed = [summary_message] + retained
        tokens_after = self.token_counter.count_messages(reconstructed)
        tokens_saved = max(0, tokens_before - tokens_after)

        return CompactionResult(
            original_message_count=n,
            compacted_message_count=len(reconstructed),
            summary_message=summary_message,
            compacted_messages=compacted,
            retained_messages=retained,
            tokens_before=tokens_before,
            tokens_after=tokens_after,
            tokens_saved=tokens_saved,
        )
