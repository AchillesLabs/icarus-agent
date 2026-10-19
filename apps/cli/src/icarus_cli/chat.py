"""Interactive Chat REPL implementation with streaming markdown and session persistence."""

import asyncio
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
                    console.print(
                        "[dim]───────────────────────────────────────────────────────[/dim]"
                    )
            except Exception as exc:
                console.print(
                    f"[yellow]Warning: Could not restore previous messages: {exc}[/yellow]"
                )

        prompt_session = InteractivePrompt(console=console, stdin=stdin)
        try:
            while True:
                try:
                    user_input = prompt_session.read_input("> ")
                except (KeyboardInterrupt, EOFError):
                    console.print("\n[dim]Exiting chat session. Goodbye![/dim]")
                    break

                cleaned = user_input.strip()
                if not cleaned:
                    continue

                if cleaned in ("/exit", "/quit"):
                    console.print("[dim]Exiting chat session. Goodbye![/dim]")
                    break

                if cleaned == "/help":
                    table = Table(
                        title="Available Slash Commands", show_header=True, header_style="bold cyan"
                    )
                    table.add_column("Command", style="bold yellow", width=15)
                    table.add_column("Description")
                    table.add_row("/help", "Display available in-chat slash commands")
                    table.add_row("/clear", "Clear the terminal screen")
                    table.add_row("/session", "Show active session details and message count")
                    table.add_row("/exit", "Exit the chat REPL")
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
                    )
                    continue

                observer = RichAgentObserver(console=console, stream_tokens=True)
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
                    elapsed_str = f"{elapsed:.1f}s" if elapsed >= 0.05 else "0s"
                    time_str = datetime.now().strftime("%I:%M %p").lstrip("0")
                    console.print(f"[dim]✻ Cogitated for {elapsed_str} · done {time_str}[/dim]\n")
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
            console.print("[dim]───────────────────────────────────────────────────────[/dim]")

        prompt_history: list[PromptMessage] = session_mgr.get_prompt_history(session.id)
        prompt_session = InteractivePrompt(console=console, stdin=stdin)

        while True:
            try:
                user_input = prompt_session.read_input("> ")
            except (KeyboardInterrupt, EOFError):
                console.print("\n[dim]Exiting chat session. Goodbye![/dim]")
                break

            cleaned = user_input.strip()
            if not cleaned:
                continue

            if cleaned in ("/exit", "/quit"):
                console.print("[dim]Exiting chat session. Goodbye![/dim]")
                break

            if cleaned == "/help":
                table = Table(
                    title="Available Slash Commands", show_header=True, header_style="bold cyan"
                )
                table.add_column("Command", style="bold yellow", width=15)
                table.add_column("Description")
                table.add_row("/help", "Display available in-chat slash commands")
                table.add_row("/models", "View and switch active model (Free vs Paid tiers)")
                table.add_row("/clear", "Clear the terminal screen")
                table.add_row("/session", "Show active session details and message count")
                table.add_row("/exit", "Exit the chat REPL")
                console.print(table)
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
                )
                continue

            # Persist user message
            session_mgr.append_message(session.id, MessageRole.USER, cleaned)
            prompt_history.append(PromptMessage(role=MessageRole.USER, content=cleaned))

            # Stream assistant response
            observer = RichAgentObserver(console=console, stream_tokens=True)

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
                elapsed_str = f"{elapsed:.1f}s" if elapsed >= 0.05 else "0s"
                time_str = datetime.now().strftime("%I:%M %p").lstrip("0")
                console.print(f"[dim]✻ Cogitated for {elapsed_str} · done {time_str}[/dim]\n")
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
