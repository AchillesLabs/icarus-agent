"""Interactive Chat REPL implementation with streaming markdown and session persistence."""

import asyncio
import random
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, TextIO

from icarus_contracts.exceptions import ProviderError
from icarus_contracts.provider import PromptMessage
from icarus_contracts.session import (
    MessageCreate,
    MessageDTO,
    MessageRole,
    SessionCreate,
    SessionDTO,
)
from icarus_core.agent import reconstruct_session_prompt_history
from icarus_core.agent.loop import AgentLoop
from icarus_core.config import ConfigManager
from icarus_core.credentials import CredentialResolver
from icarus_core.persistence.database import DatabaseManager
from icarus_core.persistence.repository import MessageRepository, SessionRepository
from icarus_core.providers import fetch_provider_models
from icarus_core.providers.base import ModelProvider
from icarus_core.providers.registry import ProviderRegistry
from icarus_core.theme import UITheme, get_theme, list_themes, set_theme
from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table

from icarus_cli.approvals import create_cli_approval_engine
from icarus_cli.models_view import render_models_table, select_model_interactive
from icarus_cli.observer import RichAgentObserver
from icarus_cli.remote import RemoteAgentClient
from icarus_cli.tui import AlternateScreenBuffer, InteractivePrompt, render_workspace_header

ACHILLES_WAR_VERBS = (
    "Strategos deliberated for",
    "Phalanx marshalled for",
    "Myrmidons deployed in",
    "War Council resolved in",
    "Achilles' vanguard struck in",
    "Tactical maneuver waged for",
    "Forged in the Aegis for",
)


def _render_timing_banner(elapsed: float) -> str:
    """Format post-turn Greek war thinking/execution duration with Achilles imagery."""
    elapsed_str = f"{elapsed:.1f}s" if elapsed >= 0.05 else "0s"
    time_str = datetime.now().strftime("%I:%M %p").lstrip("0")
    verb = random.choice(ACHILLES_WAR_VERBS)
    return f"[dim]⚔ {verb} {elapsed_str} · done {time_str}[/dim]\n"


def format_duration(seconds: float) -> str:
    """Format duration in seconds into human-readable string (e.g. 42m 16s, 12s)."""
    total_sec = max(0, int(seconds))
    if total_sec >= 3600:
        h = total_sec // 3600
        m = (total_sec % 3600) // 60
        s = total_sec % 60
        return f"{h}h {m}m {s}s"
    if total_sec >= 60:
        m = total_sec // 60
        s = total_sec % 60
        return f"{m}m {s}s"
    return f"{total_sec}s"


def render_shutdown_summary(
    console: Console,
    session_id: str,
    duration_seconds: float,
    messages: list[Any],
    theme: UITheme | None = None,
) -> None:
    """Render session finalization and shutdown summary."""
    th = theme or get_theme()
    user_count = 0
    tool_count = 0
    for m in messages:
        role = getattr(m, "role", "")
        role_val = role.value if hasattr(role, "value") else str(role)
        if role_val in (MessageRole.USER.value, "user"):
            user_count += 1
        elif role_val in (MessageRole.TOOL.value, "tool"):
            tool_count += 1
        elif getattr(m, "tool_calls", None):
            tool_count += len(m.tool_calls)

    total_msgs = len(messages)
    tool_label = "tool call" if tool_count == 1 else "tool calls"
    duration_str = format_duration(duration_seconds)

    console.print()
    console.print("[dim]Exiting chat session. Goodbye![/dim]")
    console.rule(style="dim")
    console.print("[dim]Shutting down… (finalizing session)[/dim]\n")
    console.print("Resume this session with:")
    console.print(f"  [bold {th.primary}]icarus chat --resume {session_id}[/bold {th.primary}]\n")
    console.print(f"{'Session:':<16}{session_id}")
    console.print(f"{'Duration:':<16}{duration_str}")
    console.print(f"{'Messages:':<16}{total_msgs} ({user_count} user, {tool_count} {tool_label})\n")


class ChatSessionManager:
    """Manages session resolution, loading, and persistence for chat REPL."""

    def __init__(self, db_manager: DatabaseManager | None = None) -> None:
        self.db = db_manager or DatabaseManager()
        self.session_repo = SessionRepository(self.db)
        self.message_repo = MessageRepository(self.db)

    def resolve_session(
        self,
        session_id: str | None = None,
        resume: bool = False,
    ) -> tuple[SessionDTO, bool]:
        """Resolve an existing session or create a new session based on CLI flags.

        Returns (session, was_resumed).
        """
        if session_id:
            existing = self.session_repo.get_session(session_id)
            if existing is None:
                raise ValueError(f"Session with ID '{session_id}' not found.")
            return existing, True

        if resume:
            latest = self.session_repo.get_latest_session()
            if latest is not None:
                return latest, True

        title = f"Chat {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        new_session = self.session_repo.create_session(SessionCreate(title=title, mode="chat"))
        return new_session, False

    def get_messages(self, session_id: str) -> list[MessageDTO]:
        """Fetch all messages for the active session in chronological order."""
        return self.message_repo.list_messages(session_id)

    def get_prompt_history(self, session_id: str) -> list[PromptMessage]:
        """Fetch and reconstruct active prompt history for the session honoring compactions."""
        session_messages = self.get_messages(session_id)
        return reconstruct_session_prompt_history(session_messages)

    def append_message(
        self,
        session_id: str,
        role: MessageRole | str,
        content: str | None = "",
        tool_calls: list[dict[str, Any]] | list[Any] | None = None,
        tool_call_id: str | None = None,
        name: str | None = None,
    ) -> MessageDTO:
        """Persist a new message into the session thread."""
        return self.message_repo.create_message(
            MessageCreate(
                session_id=session_id,
                role=role,
                content=content or "",
                tool_calls=tool_calls,
                tool_call_id=tool_call_id,
                name=name,
            )
        )


def _is_chat_prompt_message(msg: MessageDTO | PromptMessage) -> bool:
    """Return True if message should be preserved in prompt history for next chat turn."""
    role = getattr(msg, "role", None)
    role_val = role.value if hasattr(role, "value") else str(role)
    content = getattr(msg, "content", "") or ""
    if role_val in (MessageRole.SYSTEM.value, "system"):
        return "[Previous Conversation Summary]" in content
    return True


async def _stream_turn(
    provider: ModelProvider,
    prompt_messages: list[PromptMessage],
    model: str,
    temperature: float,
    console: Console,
) -> str:
    """Stream assistant response tokens with Rich Live display and return full content."""
    accumulated_content = ""
    with Live(
        Markdown(""), console=console, refresh_per_second=12, vertical_overflow="visible"
    ) as live:
        try:
            async for chunk in provider.stream(
                messages=prompt_messages,
                model=model,
                temperature=temperature,
            ):
                if chunk.delta:
                    accumulated_content += chunk.delta
                    live.update(Markdown(accumulated_content))
        except (KeyboardInterrupt, asyncio.CancelledError):
            live.stop()
            raise
    return accumulated_content


def _run_remote_chat(
    provider_name: str | None,
    model_name: str | None,
    session_id: str | None,
    resume: bool,
    temperature: float | None,
    auto_approve: bool,
    console: Console,
    stdin: TextIO,
    server_name: str | None,
    client: RemoteAgentClient | None,
    cfg: Any,
    cfg_manager: ConfigManager,
    theme_name: str | None = None,
) -> None:
    """Execute the interactive chat REPL loop against a remote Icarus API server."""
    should_close = False
    if client is None:
        if server_name:
            target_profile = cfg_manager.get_server(server_name)
            if not target_profile:
                console.print(
                    f"[bold red]Error:[/bold red] Server profile '{server_name}' not found."
                )
                raise ValueError(f"Server profile '{server_name}' not found.")
        else:
            target_profile = cfg_manager.get_active_server()
            if not target_profile:
                msg = (
                    "No remote server profile is active.\n"
                    "Use 'icarus server add <name> <url>' or pass '--server <name>'."
                )
                console.print(f"[bold red]Error:[/bold red] {msg}")
                raise ValueError(msg)

        api_key = cfg_manager.get_server_api_key(target_profile.name)
        remote_client = RemoteAgentClient(base_url=target_profile.url, api_key=api_key)
        should_close = True
        server_label = target_profile.name
        server_url = target_profile.url
    else:
        remote_client = client
        server_label = "remote"
        server_url = remote_client.base_url

    effective_provider = provider_name or cfg.default_provider
    effective_model = model_name or cfg.model
    effective_temp = temperature if temperature is not None else cfg.temperature

    # Resolve remote session
    try:
        if session_id:
            session_resp = asyncio.run(remote_client.get_session(session_id))
            remote_session_id = session_resp.id
            session_title = session_resp.title
            was_resumed = True
        elif resume:
            resp = asyncio.run(remote_client.list_sessions(limit=1))
            if resp.items:
                remote_session_id = resp.items[0].id
                session_title = resp.items[0].title
                was_resumed = True
            else:
                title = f"Chat {datetime.now().strftime('%Y-%m-%d %H:%M')}"
                session_resp = asyncio.run(remote_client.create_session(title=title, mode="chat"))
                remote_session_id = session_resp.id
                session_title = session_resp.title
                was_resumed = False
        else:
            title = f"Chat {datetime.now().strftime('%Y-%m-%d %H:%M')}"
            session_resp = asyncio.run(remote_client.create_session(title=title, mode="chat"))
            remote_session_id = session_resp.id
            session_title = session_resp.title
            was_resumed = False
    except Exception as exc:
        console.print(
            Panel(f"[bold red]Remote Session Error:[/bold red] {exc}", border_style="red")
        )
        if should_close:
            asyncio.run(remote_client.close())
        raise ValueError(str(exc)) from exc

    session_start_time = time.monotonic()
    active_theme = get_theme(theme_name)
    alt_buffer = AlternateScreenBuffer(stream=getattr(console, "file", sys.stdout), force=False)
    with alt_buffer:
        render_workspace_header(
            console=console,
            model=effective_model,
            provider=effective_provider,
            session_id=remote_session_id,
            tokens_used=0,
            token_budget=128000,
            mode=f"Icarus Interactive Chat (Remote: {server_label} - {server_url})",
            remote_url=server_url,
            theme=active_theme,
        )

        if was_resumed:
            try:
                messages = asyncio.run(remote_client.list_messages(remote_session_id))
                if messages:
                    console.print(
                        f"[dim]─── Restoring {len(messages)} previous message(s) ───[/dim]"
                    )
                    for msg in messages:
                        msg_role = msg.role.value if hasattr(msg.role, "value") else str(msg.role)
                        if msg_role in (MessageRole.USER.value, "user"):
                            console.print(f"[bold white]> {msg.content}[/bold white]")
                        elif msg_role in (MessageRole.TOOL.value, "tool"):
                            tool_label = msg.name or "Tool"
                            console.print(f"[dim]⚙ Tool ({tool_label}) > {msg.content}[/dim]")
                        elif msg_role in (MessageRole.ASSISTANT.value, "assistant"):
                            if msg.tool_calls:
                                tc_names = [
                                    tc.get("function", {}).get("name", "tool")
                                    if isinstance(tc, dict)
                                    else getattr(tc, "name", "tool")
                                    for tc in msg.tool_calls
                                ]
                                console.print(f"[dim]⚙ [Invoked {', '.join(tc_names)}][/dim]")
                            if msg.content:
                                console.print(f"{msg.content}")
                        elif msg_role in (MessageRole.SYSTEM.value, "system") and (
                            "[Previous Conversation Summary]" in (msg.content or "")
                        ):
                            console.print(
                                "[dim italic]📝 [Compacted Context Summary Restored][/dim italic]"
                            )
                    console.print()
            except Exception as exc:
                console.print(
                    f"[yellow]Warning: Could not restore previous messages: {exc}[/yellow]"
                )

        prompt_session = InteractivePrompt(console=console, stdin=stdin, theme=active_theme)
        try:
            while True:
                status_bar = (
                    f"[bold {active_theme.primary}]⚡ {effective_model}[/bold {active_theme.primary}] [dim]│[/dim] "
                    f"[dim]REMOTE ({server_label})[/dim] [dim]│[/dim] "
                    f"[dim]/help for commands[/dim]"
                )
                console.print(status_bar)
                try:
                    user_input = prompt_session.read_input(
                        "> ", rprompt_text=f"{effective_model} · {effective_provider}"
                    )
                except (KeyboardInterrupt, EOFError):
                    break

                cleaned = user_input.strip()
                if cleaned.startswith(">"):
                    cleaned = cleaned.lstrip("> ").strip()
                if not cleaned:
                    continue

                if cleaned in ("/exit", "/quit"):
                    break

                if cleaned == "/help":
                    table = Table(
                        title="Available Slash Commands",
                        show_header=True,
                        header_style=f"bold {active_theme.primary}",
                    )
                    table.add_column("Command", style=f"bold {active_theme.secondary}", width=20)
                    table.add_column("Description")
                    table.add_row("/help", "Display available in-chat slash commands")
                    table.add_row(
                        "/connect [id]",
                        "Connect essential tools (browser, stripe, github, slack, etc.)",
                    )
                    table.add_row(
                        "/tools [name]", "List all tools (core & MCP) or inspect parameter schemas"
                    )
                    table.add_row(
                        "/skills [pull <src>]", "List skills or pull/install from URL or repo"
                    )
                    table.add_row(
                        "/theme [name]",
                        "Change UI accent color (purple, cyan, green, amber, red, or hex)",
                    )
                    table.add_row("/clear", "Clear the terminal screen")
                    table.add_row("/session", "Show active session details and message count")
                    table.add_row("/exit", "Exit the chat REPL")
                    console.print(table)
                    continue

                if cleaned == "/connect" or cleaned.startswith("/connect "):
                    parts = cleaned.split(maxsplit=1)
                    conn_id = parts[1].strip() if len(parts) > 1 and parts[1].strip() else None
                    from icarus_cli.tools_cmd import connect_tool_interactive

                    connect_tool_interactive(console, connector_id=conn_id)
                    continue

                if cleaned == "/tools" or cleaned.startswith("/tools "):
                    parts = cleaned.split(maxsplit=1)
                    from icarus_cli.tools_cmd import render_tool_detail, render_tools_table

                    if len(parts) > 1 and parts[1].strip():
                        render_tool_detail(console, tool_name=parts[1].strip())
                    else:
                        render_tools_table(console)
                    continue

                if cleaned == "/theme" or cleaned.startswith("/theme "):
                    parts = cleaned.split(maxsplit=1)
                    if len(parts) > 1 and parts[1].strip():
                        new_theme_name = parts[1].strip()
                        try:
                            active_theme = set_theme(new_theme_name)
                            prompt_session.theme = active_theme
                            console.print(
                                f"\n[bold green]✔ UI theme changed to[/bold green] [bold {active_theme.primary}]'{active_theme.name}'[/bold {active_theme.primary}]!\n"
                            )
                        except Exception as exc:
                            console.print(f"[bold red]Theme error:[/bold red] {exc}")
                    else:
                        table = Table(
                            title="Available UI Color Themes",
                            show_header=True,
                            header_style=f"bold {active_theme.primary}",
                        )
                        table.add_column("Theme", style="bold", width=14)
                        table.add_column("Swatch", width=14)
                        table.add_column("Hex", width=12)
                        table.add_column("Description")
                        table.add_column("Status", width=12)
                        for th_name, th in list_themes().items():
                            is_active = th_name == active_theme.name
                            status = (
                                "[bold green]✔ active[/bold green]"
                                if is_active
                                else "[dim]available[/dim]"
                            )
                            table.add_row(
                                f"[{th.primary}]{th.name}[/{th.primary}]",
                                f"[{th.primary}]████████[/{th.primary}]",
                                th.primary,
                                th.description,
                                status,
                            )
                        console.print(table)
                        console.print(
                            f"[dim]* Type [bold {active_theme.primary}]/theme <name_or_hex>[/bold {active_theme.primary}] to switch theme (e.g. /theme cyan or /theme #FF007F).[/dim]\n"
                        )
                    continue

                if cleaned == "/skills" or cleaned.startswith("/skills "):
                    from icarus_core.skills import discover_skills, pull_skill

                    parts = cleaned.split(maxsplit=2)
                    subaction = parts[1].lower() if len(parts) > 1 else ""

                    if subaction in ("pull", "install", "add"):
                        if len(parts) < 3 or not parts[2].strip():
                            console.print(
                                "[yellow]Usage: [bold #C084FC]/skills pull <url_or_repo_or_path>[/bold #C084FC][/yellow]"
                            )
                            continue

                        pull_src = parts[2].strip()
                        with console.status(
                            f"[bold #C084FC]Pulling external skill from '{pull_src}'...[/bold #C084FC]"
                        ):
                            try:
                                installed_skills = pull_skill(
                                    source=pull_src,
                                    workspace_dir=Path.cwd(),
                                    overwrite=True,
                                )
                                console.print(
                                    f"\n[bold green]✔ Successfully installed {len(installed_skills)} skill(s) into workspace (.agents/skills/):[/bold green]"
                                )
                                for sk in installed_skills:
                                    console.print(
                                        f"  • [bold #E9D5FF]{sk.name}[/bold #E9D5FF] - {sk.description}\n    [dim]({sk.path})[/dim]"
                                    )
                                console.print()
                            except Exception as exc:
                                console.print(f"[bold red]Error pulling skill:[/bold red] {exc}")
                        continue

                    skills_list = discover_skills(Path.cwd())
                    table = Table(
                        title="Available Skills", show_header=True, header_style="bold #C084FC"
                    )
                    table.add_column("Skill Name", style="bold #E9D5FF", width=22)
                    table.add_column("Scope", style="dim", width=12)
                    table.add_column("Description")
                    if not skills_list:
                        table.add_row(
                            "No skills loaded",
                            "-",
                            "Add a folder with SKILL.md to .agents/skills/ or ~/.icarus/skills/",
                        )
                    else:
                        for sk in skills_list:
                            desc_snip = sk.description[:80] + (
                                "..." if len(sk.description) > 80 else ""
                            )
                            table.add_row(sk.name, sk.scope, desc_snip)
                    console.print(table)
                    continue

                if cleaned == "/session":
                    try:
                        msgs = asyncio.run(remote_client.list_messages(remote_session_id))
                        details = (
                            f"[bold cyan]Active Remote Session Details[/bold cyan]\n"
                            f"Server: [green]{server_label}[/green] ({server_url})\n"
                            f"ID: [yellow]{remote_session_id}[/yellow]\n"
                            f"Title: {session_title}\n"
                            f"Messages: {len(msgs)}"
                        )
                        console.print(Panel(details, border_style="cyan"))
                    except Exception as exc:
                        console.print(f"[bold red]Error fetching session info:[/bold red] {exc}")
                    continue

                if cleaned == "/clear":
                    console.clear()
                    render_workspace_header(
                        console=console,
                        model=effective_model,
                        provider=effective_provider,
                        session_id=remote_session_id,
                        tokens_used=0,
                        token_budget=128000,
                        remote_url=server_url,
                        theme=active_theme,
                    )
                    continue

                observer = RichAgentObserver(
                    console=console, stream_tokens=True, theme=active_theme
                )
                turn_start = time.monotonic()

                try:
                    result = asyncio.run(
                        remote_client.execute_remote_run(
                            prompt=cleaned,
                            session_id=remote_session_id,
                            model=effective_model,
                            provider=effective_provider,
                            temperature=effective_temp,
                            max_turns=cfg.max_turns,
                            auto_approve=auto_approve,
                            observer=observer,
                        )
                    )
                    console.print()
                    elapsed = max(0.0, time.monotonic() - turn_start)
                    console.print(_render_timing_banner(elapsed))
                    if result.finish_reason == "cancelled":
                        console.print("\n[bold yellow]Execution interrupted by user.[/bold yellow]")
                except (KeyboardInterrupt, asyncio.CancelledError):
                    console.print("\n[bold yellow]Generation interrupted by user.[/bold yellow]")
                    continue
                except Exception as exc:
                    console.print(
                        Panel(
                            f"[bold red]Remote Error:[/bold red] {exc}",
                            title="Error",
                            border_style="red",
                        )
                    )
                    continue

            try:
                remote_messages = asyncio.run(remote_client.list_messages(remote_session_id))
            except Exception:
                remote_messages = []
            render_shutdown_summary(
                console=console,
                session_id=remote_session_id,
                duration_seconds=max(0.0, time.monotonic() - session_start_time),
                messages=remote_messages,
                theme=active_theme,
            )
        finally:
            if should_close:
                asyncio.run(remote_client.close())


def run_chat(
    provider_name: str | None = None,
    model_name: str | None = None,
    session_id: str | None = None,
    resume: bool = False,
    temperature: float | None = None,
    auto_approve: bool = False,
    console: Console | None = None,
    stdin: TextIO | None = None,
    remote: bool = False,
    server_name: str | None = None,
    local: bool = False,
    client: RemoteAgentClient | None = None,
    theme_name: str | None = None,
) -> None:
    """Execute the interactive chat REPL loop."""
    console = console or Console()
    stdin = stdin or sys.stdin

    cfg_manager = ConfigManager()
    cfg = cfg_manager.load_config()

    is_remote = (
        remote or (server_name is not None) or (cfg_manager.get_active_server() is not None)
    ) and not local
    if is_remote:
        _run_remote_chat(
            provider_name=provider_name,
            model_name=model_name,
            session_id=session_id,
            resume=resume,
            temperature=temperature,
            auto_approve=auto_approve,
            console=console,
            stdin=stdin,
            server_name=server_name,
            client=client,
            cfg=cfg,
            cfg_manager=cfg_manager,
            theme_name=theme_name,
        )
        return

    approval_engine = create_cli_approval_engine(
        auto_approve=auto_approve, console=console, stdin=stdin
    )

    effective_provider = provider_name or cfg.default_provider
    effective_model = model_name or cfg.model
    effective_temp = temperature if temperature is not None else cfg.temperature

    session_mgr = ChatSessionManager()

    try:
        session, was_resumed = session_mgr.resolve_session(session_id=session_id, resume=resume)
    except ValueError as exc:
        console.print(Panel(f"[bold red]Session Error:[/bold red] {exc}", border_style="red"))
        raise

    if resume and not was_resumed:
        console.print("[dim]No previous session found to resume. Starting a new session.[/dim]")

    registry = ProviderRegistry()
    try:
        provider = registry.get_provider(effective_provider)
    except Exception as exc:
        console.print(
            Panel(
                f"[bold red]Provider Error:[/bold red] {exc}",
                title="Provider Error",
                border_style="red",
            )
        )
        raise

    session_start_time = time.monotonic()
    active_theme = get_theme(theme_name)
    alt_buffer = AlternateScreenBuffer(stream=getattr(console, "file", sys.stdout), force=False)
    with alt_buffer:
        total_tokens = session_mgr.message_repo.get_session_token_total(session.id)
        render_workspace_header(
            console=console,
            model=effective_model,
            provider=effective_provider,
            session_id=session.id,
            tokens_used=total_tokens,
            token_budget=getattr(cfg, "max_tokens_budget", 128000),
            theme=active_theme,
        )

        # Load existing messages for context and replay if resumed
        session_messages = session_mgr.get_messages(session.id)
        if session_messages:
            console.print(
                f"[dim]─── Restoring {len(session_messages)} previous message(s) ───[/dim]"
            )
            for msg in session_messages:
                msg_role = msg.role.value if hasattr(msg.role, "value") else str(msg.role)
                if msg_role == MessageRole.USER.value:
                    console.print(f"[bold white]> {msg.content}[/bold white]")
                elif msg_role == MessageRole.TOOL.value:
                    tool_label = msg.name or "Tool"
                    console.print(f"[dim]⚙ Tool ({tool_label}) > {msg.content}[/dim]")
                elif msg_role == MessageRole.ASSISTANT.value:
                    if msg.tool_calls:
                        tc_names = [
                            tc.get("function", {}).get("name", "tool")
                            if isinstance(tc, dict)
                            else getattr(tc, "name", "tool")
                            for tc in msg.tool_calls
                        ]
                        console.print(f"[dim]⚙ [Invoked {', '.join(tc_names)}][/dim]")
                    if msg.content:
                        console.print(f"{msg.content}")
                elif msg_role in (MessageRole.SYSTEM.value, "system") and (
                    "[Previous Conversation Summary]" in (msg.content or "")
                ):
                    console.print(
                        "[dim italic]📝 [Compacted Context Summary Restored][/dim italic]"
                    )
            console.print()

        prompt_history: list[PromptMessage] = session_mgr.get_prompt_history(session.id)
        prompt_session = InteractivePrompt(console=console, stdin=stdin, theme=active_theme)

        while True:
            total_tokens = session_mgr.message_repo.get_session_token_total(session.id)
            token_budget = getattr(cfg, "max_tokens_budget", 128000)
            pct = (total_tokens / token_budget * 100) if token_budget > 0 else 0.0
            status_bar = (
                f"[bold {active_theme.primary}]⚡ {effective_model}[/bold {active_theme.primary}] [dim]│[/dim] "
                f"[bold {active_theme.secondary}]{total_tokens:,}[/bold {active_theme.secondary}][dim]/{token_budget:,} ({pct:.1f}%)[/dim] [dim]│[/dim] "
                f"[dim]LOCAL RUNTIME[/dim] [dim]│[/dim] "
                f"[dim]/help for commands[/dim]"
            )
            console.print(status_bar)
            try:
                user_input = prompt_session.read_input(
                    "> ", rprompt_text=f"{effective_model} · {effective_provider}"
                )
            except (KeyboardInterrupt, EOFError):
                break

            cleaned = user_input.strip()
            if cleaned.startswith(">"):
                cleaned = cleaned.lstrip("> ").strip()
            if not cleaned:
                continue

            if cleaned in ("/exit", "/quit"):
                break

            if cleaned == "/help":
                table = Table(
                    title="Available Slash Commands",
                    show_header=True,
                    header_style=f"bold {active_theme.primary}",
                )
                table.add_column("Command", style=f"bold {active_theme.secondary}", width=20)
                table.add_column("Description")
                table.add_row("/help", "Display available in-chat slash commands")
                table.add_row(
                    "/connect [id]",
                    "Connect essential tools (browser, stripe, github, slack, etc.)",
                )
                table.add_row(
                    "/tools [name]", "List all tools (core & MCP) or inspect parameter schemas"
                )
                table.add_row(
                    "/skills [pull <src>]", "List skills or pull/install from URL or repo"
                )
                table.add_row(
                    "/theme [name]",
                    "Change UI accent color (purple, cyan, green, amber, red, or hex)",
                )
                table.add_row("/models", "View and switch active model (Free vs Paid tiers)")
                table.add_row("/clear", "Clear the terminal screen")
                table.add_row("/session", "Show active session details and message count")
                table.add_row("/exit", "Exit the chat REPL")
                console.print(table)
                continue

            if cleaned == "/connect" or cleaned.startswith("/connect "):
                parts = cleaned.split(maxsplit=1)
                conn_id = parts[1].strip() if len(parts) > 1 and parts[1].strip() else None
                from icarus_cli.tools_cmd import connect_tool_interactive

                connect_tool_interactive(console, connector_id=conn_id)
                continue

            if cleaned == "/tools" or cleaned.startswith("/tools "):
                parts = cleaned.split(maxsplit=1)
                from icarus_cli.tools_cmd import render_tool_detail, render_tools_table

                if len(parts) > 1 and parts[1].strip():
                    render_tool_detail(console, tool_name=parts[1].strip())
                else:
                    render_tools_table(console)
                continue

            if cleaned == "/theme" or cleaned.startswith("/theme "):
                parts = cleaned.split(maxsplit=1)
                if len(parts) > 1 and parts[1].strip():
                    new_theme_name = parts[1].strip()
                    try:
                        active_theme = set_theme(new_theme_name)
                        prompt_session.theme = active_theme
                        console.print(
                            f"\n[bold green]✔ UI theme changed to[/bold green] [bold {active_theme.primary}]'{active_theme.name}'[/bold {active_theme.primary}]!\n"
                        )
                    except Exception as exc:
                        console.print(f"[bold red]Theme error:[/bold red] {exc}")
                else:
                    table = Table(
                        title="Available UI Color Themes",
                        show_header=True,
                        header_style=f"bold {active_theme.primary}",
                    )
                    table.add_column("Theme", style="bold", width=14)
                    table.add_column("Swatch", width=14)
                    table.add_column("Hex", width=12)
                    table.add_column("Description")
                    table.add_column("Status", width=12)
                    for th_name, th in list_themes().items():
                        is_active = th_name == active_theme.name
                        status = (
                            "[bold green]✔ active[/bold green]"
                            if is_active
                            else "[dim]available[/dim]"
                        )
                        table.add_row(
                            f"[{th.primary}]{th.name}[/{th.primary}]",
                            f"[{th.primary}]████████[/{th.primary}]",
                            th.primary,
                            th.description,
                            status,
                        )
                    console.print(table)
                    console.print(
                        f"[dim]* Type [bold {active_theme.primary}]/theme <name_or_hex>[/bold {active_theme.primary}] to switch theme (e.g. /theme cyan or /theme #FF007F).[/dim]\n"
                    )
                continue

            if cleaned == "/skills" or cleaned.startswith("/skills "):
                from icarus_core.skills import discover_skills, pull_skill

                parts = cleaned.split(maxsplit=2)
                subaction = parts[1].lower() if len(parts) > 1 else ""

                if subaction in ("pull", "install", "add"):
                    if len(parts) < 3 or not parts[2].strip():
                        console.print(
                            "[yellow]Usage: [bold #C084FC]/skills pull <url_or_repo_or_path>[/bold #C084FC][/yellow]\n"
                            "[dim]Example: /skills pull https://github.com/owner/skill-repo[/dim]\n"
                            "[dim]Example: /skills pull https://raw.githubusercontent.com/.../SKILL.md[/dim]"
                        )
                        continue

                    pull_src = parts[2].strip()
                    with console.status(
                        f"[bold #C084FC]Pulling external skill from '{pull_src}'...[/bold #C084FC]"
                    ):
                        try:
                            installed_skills = pull_skill(
                                source=pull_src,
                                workspace_dir=Path.cwd(),
                                overwrite=True,
                            )
                            console.print(
                                f"\n[bold green]✔ Successfully installed {len(installed_skills)} skill(s) into workspace (.agents/skills/):[/bold green]"
                            )
                            for sk in installed_skills:
                                console.print(
                                    f"  • [bold #E9D5FF]{sk.name}[/bold #E9D5FF] - {sk.description}\n    [dim]({sk.path})[/dim]"
                                )
                            console.print()
                        except Exception as exc:
                            console.print(f"[bold red]Error pulling skill:[/bold red] {exc}")
                    continue

                skills_list = discover_skills(Path.cwd())
                table = Table(
                    title="Available Skills", show_header=True, header_style="bold #C084FC"
                )
                table.add_column("Skill Name", style="bold #E9D5FF", width=22)
                table.add_column("Scope", style="dim", width=12)
                table.add_column("Description")
                if not skills_list:
                    table.add_row(
                        "No skills loaded",
                        "-",
                        "Add a folder with SKILL.md to .agents/skills/ or ~/.icarus/skills/",
                    )
                else:
                    for sk in skills_list:
                        desc_snip = sk.description[:80] + (
                            "..." if len(sk.description) > 80 else ""
                        )
                        table.add_row(sk.name, sk.scope, desc_snip)
                console.print(table)
                console.print(
                    "[dim]* To pull an external skill, run: [bold #C084FC]/skills pull <url_or_repo>[/bold #C084FC][/dim]\n"
                    "[dim]* To create a skill, run: [bold #C084FC]icarus skills new <name>[/bold #C084FC].[/dim]\n"
                )
                continue

            if cleaned == "/models":
                cred = CredentialResolver().resolve(effective_provider)
                with console.status(f"[cyan]Fetching models for '{effective_provider}'...[/cyan]"):
                    models_list = fetch_provider_models(effective_provider, api_key=cred.secret)
                if not models_list:
                    console.print(
                        f"[yellow]No models found for provider '{effective_provider}'.[/yellow]"
                    )
                else:
                    render_models_table(
                        models_list, current_model=effective_model, provider=effective_provider
                    )
                    chosen = select_model_interactive(models_list, current_model=effective_model)
                    if chosen and chosen != effective_model:
                        effective_model = chosen
                        cfg = cfg_manager.load_config()
                        cfg.model = chosen
                        cfg_manager.save_config(cfg)
                        console.print(
                            f"[bold green]Switched active model to '{chosen}'![/bold green]"
                        )
                continue

            if cleaned == "/session":
                active_msgs = session_mgr.get_messages(session.id)
                details = (
                    f"[bold cyan]Active Session Details[/bold cyan]\n"
                    f"ID: [yellow]{session.id}[/yellow]\n"
                    f"Title: {session.title}\n"
                    f"Mode: {session.mode}\n"
                    f"Created At: {session.created_at.isoformat()}\n"
                    f"Messages: {len(active_msgs)}"
                )
                console.print(Panel(details, border_style="cyan"))
                continue

            if cleaned == "/clear":
                console.clear()
                total_tokens = session_mgr.message_repo.get_session_token_total(session.id)
                render_workspace_header(
                    console=console,
                    model=effective_model,
                    provider=effective_provider,
                    session_id=session.id,
                    tokens_used=total_tokens,
                    token_budget=getattr(cfg, "max_tokens_budget", 128000),
                    theme=active_theme,
                )
                continue

            # Persist user message
            session_mgr.append_message(session.id, MessageRole.USER, cleaned)
            prompt_history.append(PromptMessage(role=MessageRole.USER, content=cleaned))

            # Stream assistant response
            observer = RichAgentObserver(console=console, stream_tokens=True, theme=active_theme)

            def on_chat_message(msg: PromptMessage) -> None:
                session_mgr.append_message(
                    session_id=session.id,
                    role=msg.role,
                    content=msg.content or "",
                    tool_calls=msg.tool_calls,
                    tool_call_id=msg.tool_call_id,
                    name=msg.name,
                )

            agent_loop = AgentLoop(
                provider=provider,
                approval_engine=approval_engine,
                model=effective_model,
                temperature=effective_temp,
                max_turns=cfg.max_turns,
                workspace_root=Path.cwd(),
                inject_system=True,
                message_callback=on_chat_message,
            )
            turn_start = time.monotonic()
            try:
                loop_result = asyncio.run(
                    agent_loop.run(
                        messages=prompt_history,
                        observer=observer,
                    )
                )
                console.print()
                elapsed = max(0.0, time.monotonic() - turn_start)
                console.print(_render_timing_banner(elapsed))
                if loop_result.finish_reason == "cancelled":
                    console.print("\n[bold yellow]Execution interrupted by user.[/bold yellow]")
                prompt_history = [m for m in loop_result.messages if _is_chat_prompt_message(m)]
            except (KeyboardInterrupt, asyncio.CancelledError):
                console.print("\n[bold yellow]Generation interrupted by user.[/bold yellow]")
                continue
            except ProviderError as exc:
                err_title = f"{exc.__class__.__name__} ({effective_provider})"
                hint = ""
                err_str = str(exc).lower()
                if "does not exist" in err_str or "not have access" in err_str or "404" in err_str:
                    hint = (
                        "\n\n[bold yellow]Hint:[/bold yellow] The configured model "
                        f"[bold]{effective_model}[/bold] is not accessible on your API key.\n"
                        "Type [bold cyan]/models[/bold cyan] in chat or run "
                        "[bold cyan]icarus models[/bold cyan] to pick an available model."
                    )
                console.print(
                    Panel(
                        f"[bold red]{err_title}:[/bold red] {exc}{hint}",
                        title="Provider Error",
                        border_style="red",
                    )
                )
                continue
            except Exception as exc:
                console.print(
                    Panel(
                        f"[bold red]Unexpected Error:[/bold red] {exc}",
                        title="Error",
                        border_style="red",
                    )
                )
                continue

        session_messages = session_mgr.get_messages(session.id)
        render_shutdown_summary(
            console=console,
            session_id=session.id,
            duration_seconds=max(0.0, time.monotonic() - session_start_time),
            messages=session_messages,
            theme=active_theme,
        )
