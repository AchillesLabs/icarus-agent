"""Rich UI observer providing real-time streaming, tool spinners, and execution banners."""

from __future__ import annotations

import json
from typing import TextIO

from icarus_contracts.tools import ToolCall, ToolResult
from rich.console import Console
from rich.panel import Panel


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

    def on_tool_start(self, tool_call: ToolCall) -> None:
        """Display styled execution panel when a tool begins execution."""
        args = tool_call.get_arguments_dict()
        formatted_args = json.dumps(args, indent=2)

        preview = f"[bold cyan]Tool:[/bold cyan] [bold white]{tool_call.name}[/bold white]\n"
        preview += f"[bold cyan]Arguments:[/bold cyan] {formatted_args}"

        panel = Panel(
            preview,
            title=f"[bold cyan]⚙ Executing Tool: {tool_call.name}[/bold cyan]",
            border_style="cyan",
            subtitle="[dim]Autonomous ReAct Dispatch[/dim]",
        )
        self.console.print(panel)

    def on_tool_end(self, tool_result: ToolResult) -> None:
        """Display outcome summary banner with exit status and byte/char metrics."""
        if tool_result.error:
            summary = (
                f"[bold red]✖ Tool '{tool_result.name}' failed:[/bold red] {tool_result.error}"
            )
            self.console.print(Panel(summary, border_style="red"))
        else:
            output_chars = len(tool_result.output)
            summary = (
                f"[bold green]✔ Tool '{tool_result.name}' completed[/bold green] "
                f"[dim]({output_chars} characters captured)[/dim]"
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
