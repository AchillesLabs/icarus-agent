"""Interactive Chat REPL implementation with streaming markdown and session persistence."""

import asyncio
import sys
from datetime import datetime
from typing import TextIO

from icarus_contracts.exceptions import ProviderError
from icarus_contracts.provider import PromptMessage
from icarus_contracts.session import (
    MessageCreate,
    MessageDTO,
    MessageRole,
    SessionCreate,
    SessionDTO,
)
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

from icarus_cli.models_view import render_models_table, select_model_interactive


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

    def append_message(self, session_id: str, role: MessageRole | str, content: str) -> MessageDTO:
        """Persist a new message into the session thread."""
        return self.message_repo.create_message(
            MessageCreate(
                session_id=session_id,
                role=role,
                content=content,
            )
        )


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


def run_chat(
    provider_name: str | None = None,
    model_name: str | None = None,
    session_id: str | None = None,
    resume: bool = False,
    temperature: float | None = None,
    console: Console | None = None,
    stdin: TextIO | None = None,
) -> None:
    """Execute the interactive chat REPL loop."""
    console = console or Console()
    stdin = stdin or sys.stdin

    cfg_manager = ConfigManager()
    cfg = cfg_manager.load_config()

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

    banner_text = (
        f"[bold cyan]Icarus Interactive Chat[/bold cyan]\n"
        f"Session: [yellow]{session.id}[/yellow] | "
        f"Provider: [green]{effective_provider}[/green] | "
        f"Model: [green]{effective_model}[/green]\n"
        f"[dim]Type your message or use /help, /clear, /session, /exit[/dim]"
    )
    console.print(Panel(banner_text, border_style="cyan"))

    # Load existing messages for context and replay if resumed
    session_messages = session_mgr.get_messages(session.id)
    if session_messages:
        console.print(f"[dim]─── Restoring {len(session_messages)} previous message(s) ───[/dim]")
        for msg in session_messages:
            msg_role = msg.role.value if hasattr(msg.role, "value") else str(msg.role)
            if msg_role == MessageRole.USER.value:
                console.print(f"[bold cyan]You > [/bold cyan]{msg.content}")
            else:
                console.print(f"[bold green]{effective_provider} > [/bold green]{msg.content}")
        console.print("[dim]───────────────────────────────────────────────────────[/dim]")

    prompt_history: list[PromptMessage] = [
        PromptMessage(role=msg.role, content=msg.content) for msg in session_messages
    ]

    while True:
        try:
            user_input = console.input("[bold cyan]You > [/bold cyan]")
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
                    console.print(f"[bold green]Switched active model to '{chosen}'![/bold green]")
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
            console.print(Panel(banner_text, border_style="cyan"))
            continue

        # Persist user message
        session_mgr.append_message(session.id, MessageRole.USER, cleaned)
        prompt_history.append(PromptMessage(role=MessageRole.USER, content=cleaned))

        # Stream assistant response
        console.print(f"[bold green]{effective_provider} > [/bold green]")
        try:
            assistant_content = asyncio.run(
                _stream_turn(
                    provider=provider,
                    prompt_messages=prompt_history,
                    model=effective_model,
                    temperature=effective_temp,
                    console=console,
                )
            )
            if assistant_content:
                # Persist assistant message
                session_mgr.append_message(session.id, MessageRole.ASSISTANT, assistant_content)
                prompt_history.append(
                    PromptMessage(role=MessageRole.ASSISTANT, content=assistant_content)
                )
        except KeyboardInterrupt:
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
