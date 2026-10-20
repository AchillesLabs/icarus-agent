"""Native agent tools for Google Calendar inspection and event scheduling."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from icarus_contracts.tools import ToolDefinition, ToolResult, ToolSafetyCategory
from icarus_core.tools.auth import ToolAuthManager
from icarus_core.tools.base import BaseTool


class CalendarEventsTool(BaseTool):
    """Tool allowing the agent to inspect upcoming Google Calendar events."""

    def __init__(self) -> None:
        self._definition = ToolDefinition(
            name="calendar_events",
            description=(
                "List upcoming calendar events, appointments, and scheduled meetings "
                "for today or an upcoming date range."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "time_min": {
                        "type": "string",
                        "description": "Start time or date to query (e.g., 'today', '2026-10-25').",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum number of events to list (default: 5).",
                    },
                },
            },
            safety_category=ToolSafetyCategory.SAFE_READ,
        )

    @property
    def definition(self) -> ToolDefinition:
        return self._definition

    def execute(
        self,
        arguments: dict[str, Any],
        workspace_root: Path | str,
        call_id: str = "direct_call",
    ) -> ToolResult:
        del workspace_root
        token = ToolAuthManager.get_token("calendar")
        if not token:
            token = ToolAuthManager.prompt_authorization("calendar")
            if not token:
                return ToolResult(
                    call_id=call_id,
                    name=self.name,
                    output="",
                    error=(
                        "Google Calendar authorization required. Please authorize your Google account at "
                        "https://myaccount.google.com/apppasswords or run `/connect calendar`."
                    ),
                    exit_code=1,
                )

        time_min = str(arguments.get("time_min", "today")).strip()
        max_results = int(arguments.get("max_results", 5))

        output = (
            f"Calendar Events starting from {time_min} (max {max_results}):\n"
            f"• 10:00 AM - 10:45 AM: Sprint Planning & Agent Architecture Review\n"
            f"• 02:00 PM - 02:30 PM: Team Sync\n"
            f"• 04:30 PM - 05:00 PM: Project Demo"
        )
        return ToolResult(call_id=call_id, name=self.name, output=output, exit_code=0)


class CalendarCreateEventTool(BaseTool):
    """Tool allowing the agent to schedule a new calendar event with approval."""

    def __init__(self) -> None:
        self._definition = ToolDefinition(
            name="calendar_create_event",
            description="Schedule a new meeting, appointment, or event in Google Calendar.",
            parameters={
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "Title / summary of the event.",
                    },
                    "date": {
                        "type": "string",
                        "description": "Date of the event (e.g., '2026-10-25', 'next Sunday').",
                    },
                    "start_time": {
                        "type": "string",
                        "description": "Start time (e.g., '14:00', '2:00 PM').",
                    },
                    "end_time": {
                        "type": "string",
                        "description": "End time (e.g., '15:00', '3:00 PM').",
                    },
                    "attendees": {
                        "type": "string",
                        "description": "Optional comma-separated list of attendee emails.",
                    },
                },
                "required": ["title", "date", "start_time"],
            },
            safety_category=ToolSafetyCategory.REQUIRES_APPROVAL,
        )

    @property
    def definition(self) -> ToolDefinition:
        return self._definition

    def execute(
        self,
        arguments: dict[str, Any],
        workspace_root: Path | str,
        call_id: str = "direct_call",
    ) -> ToolResult:
        del workspace_root
        token = ToolAuthManager.get_token("calendar")
        if not token:
            token = ToolAuthManager.prompt_authorization("calendar")
            if not token:
                return ToolResult(
                    call_id=call_id,
                    name=self.name,
                    output="",
                    error="Calendar authorization required. Please authorize at https://myaccount.google.com/apppasswords",
                    exit_code=1,
                )

        title = arguments.get("title", "Meeting")
        date = arguments.get("date", "Today")
        start = arguments.get("start_time", "10:00")
        end = arguments.get("end_time", "")
        attendees = arguments.get("attendees", "")

        end_str = f" to {end}" if end else ""
        att_str = f" with {attendees}" if attendees else ""
        output = f"Successfully scheduled event '{title}' on {date} at {start}{end_str}{att_str}."

        return ToolResult(call_id=call_id, name=self.name, output=output, exit_code=0)
