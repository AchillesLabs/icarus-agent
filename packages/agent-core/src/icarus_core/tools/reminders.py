"""Tools for conversational background reminders and scheduled task management."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from icarus_contracts.jobs import ScheduledJobCreate, ScheduledJobStatus
from icarus_contracts.tools import ToolDefinition, ToolResult, ToolSafetyCategory
from icarus_core.persistence.database import DatabaseManager
from icarus_core.persistence.repository import ScheduledJobRepository
from icarus_core.time_parser import parse_natural_datetime
from icarus_core.tools.base import BaseTool


def format_timedelta(dt: datetime, now: datetime) -> str:
    """Format time difference into a human readable string like '1h 45m' or '25m'."""
    seconds = int((dt - now).total_seconds())
    if seconds <= 0:
        return "due now"

    days, remainder = divmod(seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, secs = divmod(remainder, 60)

    parts: list[str] = []
    if days > 0:
        parts.append(f"{days}d")
    if hours > 0:
        parts.append(f"{hours}h")
    if minutes > 0:
        parts.append(f"{minutes}m")
    if not parts or (days == 0 and hours == 0 and minutes == 0):
        parts.append(f"{secs}s")
    return " ".join(parts)


class ScheduleReminderTool(BaseTool):
    """Tool allowing the agent to schedule background reminders from natural language."""

    def __init__(self, db_manager: DatabaseManager | None = None) -> None:
        self._db_manager = db_manager

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="schedule_reminder",
            description=(
                "Schedule a background reminder or task for a future time. "
                "Parses natural language expressions (e.g. 'in 2 hours', 'in 30 mins', "
                "'tomorrow at 9am', 'at 5pm') and registers a persistent background job "
                "that triggers a desktop notification when due."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "message": {
                        "type": "string",
                        "description": "The reminder content or task description.",
                    },
                    "time": {
                        "type": "string",
                        "description": (
                            "When to trigger the reminder (e.g. 'in 2 hours', 'in 30 minutes', "
                            "'tomorrow at 9am', 'at 5pm', '2026-10-25 15:00')."
                        ),
                    },
                },
                "required": ["message", "time"],
            },
            safety_category=ToolSafetyCategory.SAFE_READ,
        )

    def execute(
        self,
        arguments: dict[str, Any],
        workspace_root: Path | str,
        call_id: str = "direct_call",
    ) -> ToolResult:
        del workspace_root
        message = str(arguments.get("message", "")).strip()
        time_str = str(arguments.get("time", "")).strip()

        if not message:
            return ToolResult(
                call_id=call_id,
                name=self.name,
                error="Parameter 'message' cannot be empty.",
                exit_code=1,
            )
        if not time_str:
            return ToolResult(
                call_id=call_id,
                name=self.name,
                error="Parameter 'time' cannot be empty.",
                exit_code=1,
            )

        now = datetime.now(UTC)
        try:
            target_dt = parse_natural_datetime(time_str, now=now)
        except ValueError as exc:
            return ToolResult(
                call_id=call_id,
                name=self.name,
                error=f"Failed to parse reminder time: {exc}",
                exit_code=1,
            )

        if target_dt <= now:
            return ToolResult(
                call_id=call_id,
                name=self.name,
                error=f"Scheduled reminder time must be in the future (parsed: {target_dt.isoformat()}).",
                exit_code=1,
            )

        try:
            db = self._db_manager or DatabaseManager()
            repo = ScheduledJobRepository(db)
            job = repo.create_job(
                ScheduledJobCreate(
                    job_type="reminder",
                    scheduled_at=target_dt,
                    payload={"message": message, "channel": "desktop"},
                    owner_id="default",
                )
            )

            time_diff = format_timedelta(target_dt, now)
            formatted_dt = target_dt.strftime("%Y-%m-%d %H:%M:%S UTC")
            output = (
                f"Successfully scheduled reminder (ID: {job.id}):\n"
                f"- Message: \"{message}\"\n"
                f"- Scheduled for: {formatted_dt} (in {time_diff})\n"
                f"- Channel: Desktop Notification"
            )
            return ToolResult(call_id=call_id, name=self.name, output=output, exit_code=0)
        except Exception as exc:
            return ToolResult(
                call_id=call_id,
                name=self.name,
                error=f"Failed to save scheduled reminder: {exc}",
                exit_code=1,
            )


class ListRemindersTool(BaseTool):
    """Tool allowing the agent to list and inspect scheduled background reminders."""

    def __init__(self, db_manager: DatabaseManager | None = None) -> None:
        self._db_manager = db_manager

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="list_reminders",
            description=(
                "List scheduled background reminders, showing trigger times, "
                "messages, and statuses."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "enum": ["pending", "completed", "all"],
                        "default": "pending",
                        "description": "Filter reminders by status: 'pending' (default), 'completed', or 'all'.",
                    },
                    "limit": {
                        "type": "integer",
                        "default": 20,
                        "description": "Maximum number of reminders to list.",
                    },
                },
            },
            safety_category=ToolSafetyCategory.SAFE_READ,
        )

    def execute(
        self,
        arguments: dict[str, Any],
        workspace_root: Path | str,
        call_id: str = "direct_call",
    ) -> ToolResult:
        del workspace_root
        status_filter = str(arguments.get("status", "pending")).lower().strip()
        limit = int(arguments.get("limit", 20))

        if status_filter == "pending":
            target_status: ScheduledJobStatus | None = ScheduledJobStatus.PENDING
        elif status_filter == "completed":
            target_status = ScheduledJobStatus.COMPLETED
        else:
            target_status = None

        try:
            db = self._db_manager or DatabaseManager()
            repo = ScheduledJobRepository(db)
            jobs = repo.list_jobs(
                owner_id="default",
                status=target_status,
                job_type="reminder",
                limit=limit,
            )

            if not jobs:
                status_desc = f" ({status_filter})" if status_filter != "all" else ""
                return ToolResult(
                    call_id=call_id,
                    name=self.name,
                    output=f"No scheduled reminders found{status_desc}.",
                    exit_code=0,
                )

            now = datetime.now(UTC)
            lines = [f"Found {len(jobs)} reminder(s):"]
            for j in jobs:
                payload = j.payload or {}
                msg = payload.get("message", "Reminder")
                sched_str = j.scheduled_at.strftime("%Y-%m-%d %H:%M:%S UTC")
                diff_str = (
                    f"in {format_timedelta(j.scheduled_at, now)}"
                    if j.scheduled_at > now
                    else f"{format_timedelta(now, j.scheduled_at)} ago"
                )
                lines.append(
                    f"- [{j.status.value.upper()}] ID: {j.id[:8]}... | {sched_str} ({diff_str})\n"
                    f"  Message: \"{msg}\""
                )

            return ToolResult(call_id=call_id, name=self.name, output="\n".join(lines), exit_code=0)
        except Exception as exc:
            return ToolResult(
                call_id=call_id,
                name=self.name,
                error=f"Failed to query scheduled reminders: {exc}",
                exit_code=1,
            )
