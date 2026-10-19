"""Rich UI observer providing real-time streaming, tool spinners, and execution banners."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, TextIO

from icarus_contracts.tools import ToolCall, ToolResult
from rich.console import Console
from rich.panel import Panel

if TYPE_CHECKING:
    from icarus_contracts.context import CompactionResult


class RichAgentObserver:
    """AgentLoop observer rendering real-time terminal output via Rich."""

    def __init__(
        self,
        console: Console | None = None,
        stdout: TextIO | None = None,
        stream_tokens: bool = True,
    ) -> None:
        self.console = console or Console()
        self.stdout = stdout
        self.stream_tokens = stream_tokens
        self._current_status = None

    def on_token(self, delta: str) -> None:
        """Stream token deltas directly to configured output stream."""
        if not self.stream_tokens or not delta:
            return
        if self.stdout is not None:
            self.stdout.write(delta)
            self.stdout.flush()
        else:
            self.console.print(delta, end="")

    def on_turn_start(self, turn: int) -> None:
        """Render turn transition banner for multi-turn reasoning cycles."""
        if turn > 1:
            self.console.print(f"\n[dim]─── Reasoning (Turn {turn}) ───[/dim]\n")

    def on_turn_end(self, turn: int) -> None:
        """Invoked when turn reasoning concludes."""
        pass

    def _classify_tool(self, name: str) -> tuple[str, str, str, str]:
        """Classify tool name into (icon, category, border_style, subtitle)."""
        lower = name.lower()
        if "mcp" in lower or lower.startswith("mcp_"):
            return "🔌", "Model Context Protocol (MCP)", "blue", "Official MCP Server Dispatch"
        if "web_search" in lower or "search" in lower:
            return "🌐", "Web Intelligence Search", "cyan", "Live Web Intelligence"
        if "fetch_webpage" in lower or "browser" in lower or "puppeteer" in lower or "playwright" in lower:
            return "🖥", "Browser Automation", "magenta", "Autonomous Web Navigation & Extraction"
        if "reminder" in lower or "schedule" in lower or "job" in lower:
            return "⏰", "Background Task Scheduler", "yellow", "Autonomous Executive Reminders"
        return "⚙", "Tool Execution", "cyan", "Autonomous ReAct Dispatch"

    def on_tool_start(self, tool_call: ToolCall) -> None:
        """Display styled execution panel when a tool begins execution."""
        icon, category, border_style, subtitle = self._classify_tool(tool_call.name)
        args = tool_call.get_arguments_dict()
        formatted_args = json.dumps(args, indent=2)

        preview = f"[bold white]Tool:[/bold white] [bold {border_style}]{tool_call.name}[/bold {border_style}]\n"
        preview += f"[bold white]Arguments:[/bold white] {formatted_args}"

        panel = Panel(
            preview,
            title=f"[bold {border_style}]{icon} {category}: {tool_call.name}[/bold {border_style}]",
            border_style=border_style,
            subtitle=f"[dim]{subtitle}[/dim]",
        )
        self.console.print(panel)

    def on_tool_end(self, tool_result: ToolResult) -> None:
        """Display outcome summary banner with exit status and byte/char metrics."""
        icon, category, border_style, _ = self._classify_tool(tool_result.name)
        if tool_result.error:
            summary = (
                f"[bold red]✖ Tool '{tool_result.name}' failed:[/bold red] {tool_result.error}"
            )
            self.console.print(Panel(summary, border_style="red"))
        else:
            output_chars = len(tool_result.output)
            output_lines = [line.strip() for line in tool_result.output.splitlines() if line.strip()]
            preview_snippet = ""
            if output_lines:
                first_line = output_lines[0]
                if len(first_line) > 120:
                    first_line = first_line[:117] + "..."
                preview_snippet = f"\n[dim]Preview: {first_line}[/dim]"

            summary = (
                f"[bold green]✔ {icon} {tool_result.name} completed[/bold green] "
                f"[dim]({output_chars:,} characters captured)[/dim]{preview_snippet}"
            )
            self.console.print(Panel(summary, border_style="green"))

    def on_max_turns(self, max_turns: int) -> None:
        """Display clear notice panel when maximum turn budget is reached."""
        summary = (
            f"[bold yellow]Execution Budget Limit Reached:[/bold yellow] "
            f"Maximum turn budget ({max_turns} turns) reached. Halting loop."
        )
        self.console.print(
            Panel(
                summary,
                title="[bold yellow]Execution Budget Limit[/bold yellow]",
                border_style="yellow",
            )
        )

    def on_compaction(self, event: CompactionResult) -> None:
        """Display styled compaction notice when older history is summarized."""
        summary = (
            f"[bold magenta]⚡ Context Compaction Executed:[/bold magenta] "
            f"Summarized older turns "
            f"({event.original_message_count} → {event.compacted_message_count} messages).\n"
            f"[dim]Tokens Saved:[/dim] [bold white]~{event.tokens_saved}[/bold white] "
            f"[dim](reduced from {event.tokens_before} to {event.tokens_after})[/dim]"
        )
        self.console.print(
            Panel(
                summary,
                title="[bold magenta]⚡ Context Management[/bold magenta]",
                border_style="magenta",
            )
        )

    def on_max_tokens(self, max_tokens: int) -> None:
        """Display clear notice panel when maximum token budget is reached."""
        summary = (
            f"[bold yellow]Token Budget Ceiling Reached:[/bold yellow] "
            f"Maximum total tokens ({max_tokens} tokens) reached. Halting loop."
        )
        self.console.print(
            Panel(
                summary,
                title="[bold yellow]Token Budget Limit[/bold yellow]",
                border_style="yellow",
            )
        )
