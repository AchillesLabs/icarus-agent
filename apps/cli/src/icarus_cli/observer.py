"""Rich UI observer providing real-time streaming, tool spinners, and execution banners."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, TextIO

from icarus_contracts.tools import ToolCall, ToolResult
from icarus_core.theme import UITheme, get_theme
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
        theme: UITheme | None = None,
    ) -> None:
        self.console = console or Console()
        self.stdout = stdout
        self.stream_tokens = stream_tokens
        self.theme = theme or get_theme()
        self._current_status = None
        self._active_step_lines = 0
        self._assistant_header_printed = False

    def on_token(self, delta: str) -> None:
        """Stream token deltas directly to configured output stream."""
        if not self.stream_tokens or not delta:
            return
        if not self._assistant_header_printed:
            if self.stdout is not None:
                self.stdout.write("\n● Icarus\n")
                self.stdout.flush()
            else:
                self.console.print(
                    f"\n[bold {self.theme.primary}]● Icarus[/bold {self.theme.primary}]"
                )
            self._assistant_header_printed = True

        cleaned_delta = delta.replace("<br>", "\n").replace("<br/>", "\n").replace("<br />", "\n")
        if self.stdout is not None:
            self.stdout.write(cleaned_delta)
            self.stdout.flush()
        else:
            self.console.print(cleaned_delta, end="", highlight=False)

    def on_turn_start(self, turn: int) -> None:
        """Invoked when turn reasoning begins. Multi-turn reasoning flows seamlessly."""
        self._assistant_header_printed = False

    def on_turn_end(self, turn: int) -> None:
        """Invoked when turn reasoning concludes."""
        pass

    def _format_action_labels(self, name: str, args: dict[str, Any]) -> tuple[str, str, str]:
        """Return (active_action, active_detail, completed_verb) for tool call."""
        lower = name.lower()
        if "location" in lower:
            return (
                "Resolving location",
                f"Querying high-precision OS WiFi/GPS telemetry ({name})...",
                "Resolved location",
            )
        if "command" in lower or lower in ("bash", "sh", "terminal", "exec"):
            cmd = str(args.get("command") or args.get("CommandLine") or args.get("cmd") or "")
            short_cmd = cmd.strip()
            if len(short_cmd) > 50:
                short_cmd = short_cmd[:47] + "..."
            return (
                "Running command",
                f"$ {short_cmd} ({name})"
                if short_cmd
                else f"Executing shell command via {name}...",
                f"Ran {short_cmd}" if short_cmd else f"Ran {name}",
            )
        if "view_file" in lower or "read_file" in lower or "read_url_content" in lower:
            target = str(args.get("path") or args.get("AbsolutePath") or args.get("Url") or "")
            short_target = target.replace("\\", "/").split("/")[-1] if target else "file"
            return (
                f"Reading {short_target}",
                f"{name}: {target}" if target else f"Reading file contents via {name}...",
                f"Read {short_target}",
            )
        if (
            "edit" in lower
            or "write_to_file" in lower
            or "replace_file" in lower
            or "write_file" in lower
        ):
            target = str(args.get("path") or args.get("TargetFile") or "")
            short_target = target.replace("\\", "/").split("/")[-1] if target else "file"
            return (
                f"Editing {short_target}",
                f"{name}: {target}" if target else f"Applying modifications via {name}...",
                f"Edited {short_target}",
            )
        if "search" in lower:
            q = str(args.get("query") or args.get("q") or "")
            short_q = f'"{q}"' if q else "web"
            return (
                f"Searching web for {short_q}",
                f"Querying web intelligence ({name})...",
                f"Searched {short_q}",
            )
        if "fetch" in lower or "browser" in lower:
            url = str(args.get("url") or args.get("Url") or "")
            return (
                "Fetching webpage",
                f"{name}: {url}" if url else f"Navigating via {name}...",
                "Fetched webpage",
            )

        readable = name.replace("_", " ").title()
        arg_snippets = []
        for k, v in list(args.items())[:2]:
            v_str = str(v)
            if len(v_str) > 30:
                v_str = v_str[:27] + "..."
            arg_snippets.append(f"{k}={v_str!r}")
        args_display = f"({', '.join(arg_snippets)})" if arg_snippets else "()"
        return (
            f"Executing {name}",
            f"Dispatching with {args_display}",
            f"{readable} completed",
        )

    def on_tool_start(self, tool_call: ToolCall) -> None:
        """Display step banner when a tool begins execution."""
        args = tool_call.get_arguments_dict()
        action, detail, _ = self._format_action_labels(tool_call.name, args)

        self.console.print(
            f"  [bold cyan]●[/bold cyan] [bold white]{action}[/bold white] [dim]v[/dim]\n"
            f"    [dim]{detail}[/dim]",
            highlight=False,
        )
        self._active_step_lines = 2

    def on_tool_end(self, tool_result: ToolResult) -> None:
        """Collapse active step and display completed summary."""
        import sys

        if self._active_step_lines > 0:
            try:
                if hasattr(sys.stdout, "isatty") and sys.stdout.isatty():
                    clear_seq = ("\033[A\033[2K" * self._active_step_lines) + "\r"
                    sys.stdout.write(clear_seq)
                    sys.stdout.flush()
            except Exception:
                pass
            self._active_step_lines = 0

        _, _, completed_verb = self._format_action_labels(tool_result.name, {})

        if tool_result.error:
            err_snip = tool_result.error.strip()
            if len(err_snip) > 60:
                err_snip = err_snip[:57] + "..."
            self.console.print(
                f"  [bold red]✖[/bold red] [bold red]{tool_result.name} failed[/bold red] [dim]›[/dim] [red]{err_snip}[/red]",
                highlight=False,
            )
            return

        if "location" in tool_result.name.lower():
            out = tool_result.output
            summary_parts = []
            for line in out.splitlines():
                line_str = line.strip()
                if "City:" in line_str:
                    city_val = line_str.split("City:", 1)[1].strip()
                    summary_parts.append(city_val)
                elif "Postal Code:" in line_str:
                    pin_val = line_str.split("Postal Code:", 1)[1].strip()
                    summary_parts.append(f"({pin_val})")
            if summary_parts:
                loc_summary = " ".join(summary_parts)
                self.console.print(
                    f"  [bold green]✔[/bold green] [bold white]Resolved location[/bold white] [dim]›[/dim] [cyan]{loc_summary}[/cyan]",
                    highlight=False,
                )
                return

        self.console.print(
            f"  [bold green]✔[/bold green] [bold white]{completed_verb}[/bold white]",
            highlight=False,
        )

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
