"""Non-interactive one-shot CLI execution handler with token streaming and persistence."""

from __future__ import annotations

import asyncio
import sys
from datetime import datetime
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
    messages = [PromptMessage(role=MessageRole.USER, content=prompt)]

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
        assistant_content = asyncio.run(
            _stream_run(
                provider=provider,
                prompt=effective_prompt,
                model=effective_model,
                temperature=effective_temp,
                stdout=stdout_stream,
            )
        )
        # Record assistant message
        if assistant_content:
            message_repo.create_message(
                MessageCreate(
                    session_id=session.id,
                    role=MessageRole.ASSISTANT,
                    content=assistant_content,
                )
            )

        run_repo.update_run(
            run.id,
            status=RunStatus.SUCCEEDED,
            completed=True,
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
        )
        return 1
