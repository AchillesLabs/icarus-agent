"""Non-interactive one-shot CLI execution handler with token streaming and persistence."""

from __future__ import annotations

import asyncio
import sys
from datetime import datetime
from pathlib import Path
from typing import TextIO

from icarus_contracts.exceptions import ProviderError
from icarus_contracts.provider import PromptMessage
from icarus_contracts.session import (
    MessageCreate,
    MessageRole,
    RunCreate,
    RunStatus,
    SessionCreate,
)
from icarus_core.agent.loop import AgentLoop
from icarus_core.agent.prompts import inject_system_prompt
from icarus_core.config import ConfigManager
from icarus_core.logging import get_logger, redact_secrets, setup_logging
from icarus_core.persistence.database import DatabaseManager
from icarus_core.persistence.repository import (
    AgentRunRepository,
    MessageRepository,
    SessionRepository,
)
from icarus_core.providers.base import ModelProvider
from icarus_core.providers.registry import ProviderRegistry
from rich.console import Console

from icarus_cli.approvals import create_cli_approval_engine
from icarus_cli.observer import RichAgentObserver

logger = get_logger("cli.run")


async def _stream_run(
    provider: ModelProvider,
    prompt: str,
    model: str,
    temperature: float,
    stdout: TextIO,
) -> str:
    """Stream model response tokens directly to stdout."""
    accumulated: list[str] = []
    messages = inject_system_prompt([PromptMessage(role=MessageRole.USER, content=prompt)])

    async for chunk in provider.stream(
        messages=messages,
        model=model,
        temperature=temperature,
    ):
        if chunk.delta:
            accumulated.append(chunk.delta)
            stdout.write(chunk.delta)
            stdout.flush()

    result = "".join(accumulated)
    if result and not result.endswith("\n"):
        stdout.write("\n")
        stdout.flush()

    return result


def execute_run(
    prompt: str | None = None,
    provider_name: str | None = None,
    model_name: str | None = None,
    temperature: float | None = None,
    auto_approve: bool = False,
    console: Console | None = None,
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
) -> int:
    """Execute one-shot prompt execution, stream tokens to stdout, and return POSIX exit code.

    Exit codes:
      0: Success
      1: Provider or configuration error / invalid input
      130: User cancellation via SIGINT (Ctrl+C)
    """
    console = console or Console()
    stdin_stream = stdin or sys.stdin
    stdout_stream = stdout or sys.stdout

    setup_logging()
    _approval_engine = create_cli_approval_engine(
        auto_approve=auto_approve, console=console, stdin=stdin_stream
    )

    # Resolve input prompt from CLI argument or stdin pipe
    effective_prompt = prompt
    if effective_prompt is None or effective_prompt.strip() == "-":
        if prompt is None and hasattr(stdin_stream, "isatty") and stdin_stream.isatty():
            effective_prompt = None
        else:
            try:
                effective_prompt = stdin_stream.read()
            except Exception as exc:
                logger.error("Failed to read from standard input: %s", exc)
                effective_prompt = None

    if effective_prompt:
        effective_prompt = effective_prompt.strip()

    if not effective_prompt:
        console.print(
            "[bold red]Error:[/bold red] No prompt provided. "
            "Pass a prompt argument or pipe text via standard input."
        )
        logger.warning("One-shot run aborted: empty prompt provided.")
        return 1

    cfg_manager = ConfigManager()
    cfg = cfg_manager.load_config()

    effective_provider = provider_name or cfg.default_provider
    effective_model = model_name or cfg.model
    effective_temp = temperature if temperature is not None else cfg.temperature

    logger.info(
        "Initiating one-shot run with provider=%s model=%s temp=%.2f",
        effective_provider,
        effective_model,
        effective_temp,
    )

    db_mgr = DatabaseManager()
    session_repo = SessionRepository(db_mgr)
    message_repo = MessageRepository(db_mgr)
    run_repo = AgentRunRepository(db_mgr)

    # Register persistence session and agent run
    session_title = f"Run {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    session = session_repo.create_session(SessionCreate(title=session_title, mode="run"))
    run = run_repo.create_run(
        RunCreate(
            session_id=session.id,
            provider=effective_provider,
            model=effective_model,
            status=RunStatus.RUNNING,
        )
    )

    # Record user message
    message_repo.create_message(
        MessageCreate(
            session_id=session.id,
            role=MessageRole.USER,
            content=effective_prompt,
        )
    )

    registry = ProviderRegistry()
    try:
        provider = registry.get_provider(effective_provider)
    except Exception as exc:
        safe_msg = redact_secrets(str(exc))
        err_msg = f"Failed to initialize provider '{effective_provider}': {safe_msg}"
        console.print(f"[bold red]Provider error:[/bold red] {err_msg}")
        logger.error(err_msg, exc_info=True)
        run_repo.update_run(
            run.id,
            status=RunStatus.FAILED,
            error_category="ProviderInitError",
            completed=True,
        )
        return 1

    try:
        approval_engine = create_cli_approval_engine(
            auto_approve=auto_approve, console=console, stdin=stdin_stream
        )
        observer = RichAgentObserver(
            console=console,
            stdout=stdout_stream,
            stream_tokens=True,
        )

        def on_run_message(msg: PromptMessage) -> None:
            message_repo.create_message(
                MessageCreate(
                    session_id=session.id,
                    role=msg.role,
                    content=msg.content or "",
                    tool_calls=msg.tool_calls,
                    tool_call_id=msg.tool_call_id,
                    name=msg.name,
                )
            )

        agent_loop = AgentLoop(
            provider=provider,
            approval_engine=approval_engine,
            model=effective_model,
            temperature=effective_temp,
            max_turns=cfg.max_turns,
            workspace_root=Path.cwd(),
            inject_system=True,
            message_callback=on_run_message,
        )

        loop_result = asyncio.run(
            agent_loop.run(
                prompt=effective_prompt,
                observer=observer,
            )
        )
        assistant_content = loop_result.content
        if stdout_stream and assistant_content and not assistant_content.endswith("\n"):
            stdout_stream.write("\n")
            stdout_stream.flush()

        if loop_result.finish_reason == "cancelled":
            console.print("\n[bold yellow]Run interrupted by user.[/bold yellow]")
            logger.warning("One-shot run interrupted by SIGINT / user cancellation.")
            run_repo.update_run(
                run.id,
                status=RunStatus.CANCELLED,
                completed=True,
                budget_counters=loop_result.budget_counters,
            )
            return 130

        run_repo.update_run(
            run.id,
            status=RunStatus.SUCCEEDED,
            completed=True,
            budget_counters=loop_result.budget_counters,
        )
        logger.info("One-shot run completed successfully (chars=%d).", len(assistant_content))
        return 0

    except (KeyboardInterrupt, asyncio.CancelledError):
        console.print("\n[bold yellow]Run interrupted by user.[/bold yellow]")
        logger.warning("One-shot run interrupted by SIGINT / user cancellation.")
        run_repo.update_run(
            run.id,
            status=RunStatus.CANCELLED,
            completed=True,
            budget_counters={
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "model_calls": 0,
                "tool_calls": 0,
                "compaction_count": 0,
                "elapsed_time_seconds": 0.0,
                "turns": 0,
                "compactions": 0,
                "finish_reason": "cancelled",
            },
        )
        return 130

    except ProviderError as exc:
        err_type = exc.__class__.__name__
        safe_msg = redact_secrets(str(exc))
        console.print(f"[bold red]Provider error ({err_type}):[/bold red] {safe_msg}")
        logger.error("Provider error encountered during generation: %s", exc)
        run_repo.update_run(
            run.id,
            status=RunStatus.FAILED,
            error_category=err_type,
            completed=True,
            budget_counters={
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "model_calls": 0,
                "tool_calls": 0,
                "compaction_count": 0,
                "elapsed_time_seconds": 0.0,
                "turns": 0,
                "compactions": 0,
                "finish_reason": "error",
            },
        )
        return 1

    except Exception as exc:
        safe_msg = redact_secrets(str(exc))
        console.print(f"[bold red]Execution error:[/bold red] {safe_msg}")
        logger.error("Unexpected error during one-shot run: %s", exc, exc_info=True)
        run_repo.update_run(
            run.id,
            status=RunStatus.FAILED,
            error_category="UnexpectedError",
            completed=True,
            budget_counters={
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "model_calls": 0,
                "tool_calls": 0,
                "compaction_count": 0,
                "elapsed_time_seconds": 0.0,
                "turns": 0,
                "compactions": 0,
                "finish_reason": "error",
            },
        )
        return 1
