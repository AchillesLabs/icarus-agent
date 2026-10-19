"""Execution handlers for background jobs (AgentLoop runs, reminders, notifications)."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

from icarus_contracts import (
    MessageCreate,
    MessageRole,
    PromptMessage,
    RunCreate,
    RunStatus,
    ScheduledJobDTO,
    SessionCreate,
)
from icarus_core.agent.approvals import ApprovalEngine, ApprovalPolicy
from icarus_core.agent.loop import AgentLoop
from icarus_core.persistence.database import DatabaseManager
from icarus_core.persistence.repository import (
    TenantCredentialRepository,
    TenantMessageRepository,
    TenantRunRepository,
    TenantSessionRepository,
)
from icarus_core.providers.base import ModelProvider
from icarus_core.providers.registry import ProviderRegistry
from icarus_core.security import CredentialVault, redact_secret
from icarus_core.tools.registry import ToolRegistry, create_default_registry

from icarus_worker.config import WorkerSettings


@dataclass
class JobContext:
    """Shared execution context provided to job handlers."""

    worker_id: str
    db_manager: DatabaseManager
    settings: WorkerSettings
    provider_registry: ProviderRegistry | None = None
    tool_registry: ToolRegistry | None = None
    approval_engine: ApprovalEngine | None = None
    vault: CredentialVault | None = None


class JobHandler(Protocol):
    """Protocol for job execution handlers."""

    async def handle(self, job: ScheduledJobDTO, context: JobContext) -> dict[str, Any] | None:
        """Execute the job and return an optional dictionary of results to record."""
        ...


class AgentRunJobHandler:
    """Handler executing headless AgentLoop runs for background tasks and scheduled prompts."""

    async def handle(self, job: ScheduledJobDTO, context: JobContext) -> dict[str, Any] | None:
        payload = job.payload or {}
        prompt = payload.get("prompt", "")
        session_id = payload.get("session_id")
        provider_name = payload.get("provider") or context.settings.default_provider
        model_name = payload.get("model") or context.settings.default_model
        temperature = float(payload.get("temperature", 0.7))
        max_turns = int(payload.get("max_turns", 25))
        max_total_tokens = payload.get("max_total_tokens")
        auto_compact = bool(payload.get("auto_compact", True))

        # Tenant-scoped persistence
        session_repo = TenantSessionRepository(context.db_manager, owner_id=job.owner_id)
        message_repo = TenantMessageRepository(context.db_manager, owner_id=job.owner_id)
        run_repo = TenantRunRepository(context.db_manager, owner_id=job.owner_id)

        # Ensure session exists or create a new dedicated background session
        if session_id:
            session = session_repo.get_session(session_id)
            if session is None:
                session = session_repo.create_session(
                    SessionCreate(title=f"Background Run: {job.job_type}")
                )
                session_id = session.id
        else:
            session = session_repo.create_session(
                SessionCreate(title=f"Scheduled Job: {job.job_type}")
            )
            session_id = session.id

        # Append prompt to session if provided
        if prompt:
            message_repo.create_message(
                MessageCreate(
                    session_id=session_id,
                    role=MessageRole.USER,
                    content=prompt,
                )
            )

        # Create AgentRun record
        run = run_repo.create_run(
            RunCreate(
                session_id=session_id,
                status=RunStatus.RUNNING,
                provider=provider_name,
                model=model_name,
            )
        )

        # Resolve provider with BYOK credentials if vault is available
        provider_registry = context.provider_registry or ProviderRegistry()
        byok_key: str | None = None
        if context.vault is not None:
            cred_repo = TenantCredentialRepository(
                db_manager=context.db_manager,
                owner_id=job.owner_id,
                vault=context.vault,
            )
            byok_key = cred_repo.get_decrypted_secret(provider_name)
        allow_fallback = getattr(context.settings, "allow_fallback_to_system_credentials", True)
        provider: ModelProvider = provider_registry.get_provider(
            provider_name,
            api_key=byok_key,
            allow_fallback=allow_fallback,
        )

        # Setup headless approvals (all automated/approved for background runs)
        approval_engine = context.approval_engine or ApprovalEngine(
            policy=ApprovalPolicy.AUTO_APPROVE
        )
        tool_registry = context.tool_registry or create_default_registry()

        def _on_run_message(msg: PromptMessage) -> None:
            if msg.role != "system":
                role_val = (
                    MessageRole(msg.role)
                    if msg.role in MessageRole._value2member_map_
                    else MessageRole.ASSISTANT
                )
                safe_content = redact_secret(msg.content or "", byok_key)
                safe_tools = redact_secret(msg.tool_calls, byok_key)
                message_repo.create_message(
                    MessageCreate(
                        session_id=session_id,
                        role=role_val,
                        content=safe_content,
                        tool_calls=safe_tools,
                        tool_call_id=msg.tool_call_id,
                        name=msg.name,
                    )
                )

        # Build prompt messages from session history
        history = message_repo.list_messages(session_id)
        prompt_messages = [
            PromptMessage(
                role=m.role.value if hasattr(m.role, "value") else str(m.role),
                content=m.content or "",
                tool_calls=m.tool_calls,
                tool_call_id=m.tool_call_id,
                name=m.name,
            )
            for m in history
        ]

        agent_loop = AgentLoop(
            provider=provider,
            tool_registry=tool_registry,
            approval_engine=approval_engine,
            model=model_name,
            temperature=temperature,
            max_turns=max_turns,
            max_total_tokens=max_total_tokens,
            auto_compact=auto_compact,
            inject_system=True,
            message_callback=_on_run_message,
        )

        try:
            loop_result = await agent_loop.run(messages=prompt_messages)
            if loop_result.finish_reason == "cancelled":
                run_repo.update_run(
                    run.id,
                    status=RunStatus.CANCELLED,
                    completed=True,
                    budget_counters=loop_result.budget_counters,
                )
            else:
                run_repo.update_run(
                    run.id,
                    status=RunStatus.SUCCEEDED,
                    completed=True,
                    budget_counters=loop_result.budget_counters,
                )

            safe_resp = redact_secret(loop_result.content or "", byok_key)
            return {
                "run_id": run.id,
                "session_id": session_id,
                "finish_reason": loop_result.finish_reason,
                "budget_counters": loop_result.budget_counters,
                "response": safe_resp,
            }
        except Exception as exc:
            run_repo.update_run(
                run.id,
                status=RunStatus.FAILED,
                completed=True,
                error_category=type(exc).__name__,
            )
            raise


class NotificationJobHandler:
    """Handler for reminders, alerts, and asynchronous notifications."""

    def __init__(self, delivery_callback: Callable[[dict[str, Any]], None] | None = None) -> None:
        self.delivery_callback = delivery_callback

    async def handle(self, job: ScheduledJobDTO, context: JobContext) -> dict[str, Any] | None:
        payload = job.payload or {}
        message = payload.get("message") or payload.get("text") or f"Reminder: {job.job_type}"
        recipient = payload.get("recipient")
        channel = payload.get("channel", "desktop")

        desktop_notified = False
        if channel in ("desktop", "all") or job.job_type in ("reminder", "alert", "notification"):
            try:
                from icarus_core.notifications import send_desktop_notification

                title = f"Icarus {job.job_type.title()}"
                desktop_notified = send_desktop_notification(title=title, message=message)
            except Exception:
                desktop_notified = False

        result = {
            "job_id": job.id,
            "job_type": job.job_type,
            "message": message,
            "recipient": recipient,
            "channel": channel,
            "desktop_notified": desktop_notified,
            "dispatched_at": datetime.now(UTC).isoformat(),
            "status": "delivered",
        }

        if self.delivery_callback is not None:
            self.delivery_callback(result)

        return result


class HandlerRegistry:
    """Registry maintaining job handlers keyed by job_type name."""

    def __init__(self) -> None:
        self._handlers: dict[str, JobHandler] = {}

    def register(self, job_type: str, handler: JobHandler) -> None:
        """Register a handler for a specific job_type."""
        self._handlers[job_type.lower().strip()] = handler

    def get(self, job_type: str) -> JobHandler | None:
        """Lookup a registered handler for a job_type."""
        return self._handlers.get(job_type.lower().strip())

    @classmethod
    def default_registry(cls) -> "HandlerRegistry":
        """Construct a registry with standard built-in handlers."""
        registry = cls()
        agent_handler = AgentRunJobHandler()
        registry.register("agent_run", agent_handler)
        registry.register("agent_task", agent_handler)
        registry.register("run", agent_handler)

        notification_handler = NotificationJobHandler()
        registry.register("notification", notification_handler)
        registry.register("reminder", notification_handler)
        registry.register("alert", notification_handler)
        return registry
