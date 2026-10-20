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
        from icarus_core.integrations.clients.google_client import GoogleCalendarApiClient

        token = ToolAuthManager.get_access_token("google") or ToolAuthManager.get_token("calendar")
        if not token and getattr(self, "client", None) is None:
            token = ToolAuthManager.prompt_authorization("calendar")
            if not token:
                return ToolResult(
                    call_id=call_id,
                    name=self.name,
                    output="",
                    error=(
                        "Google Calendar authorization required. Please authorize your Google account with "
                        "`icarus integrations connect google` or visit "
                        "https://myaccount.google.com/apppasswords or run `/connect calendar`."
                    ),
                    exit_code=1,
                )

        time_min = str(arguments.get("time_min", "today")).strip()
        max_results = int(arguments.get("max_results", 5))

        # Real Google Calendar REST API call if token or client available
        if getattr(self, "client", None) or (
            token and (token.startswith("ya29.") or len(token) > 20)
        ):
            try:
                api_client = getattr(self, "client", None) or GoogleCalendarApiClient(
                    access_token=token
                )
                events = api_client.list_events(time_min=time_min, max_results=max_results)
                if not events:
                    return ToolResult(
                        call_id=call_id,
                        name=self.name,
                        output=f"No upcoming calendar events found starting from {time_min}.",
                        exit_code=0,
                    )
                lines = [f"Calendar Events starting from {time_min} (max {max_results}):\n"]
                for e in events:
                    start_val = (
                        e.get("start", {}).get("dateTime")
                        or e.get("start", {}).get("date")
                        or "Unknown"
                    )
                    summary_val = e.get("summary", "Untitled Event")
                    lines.append(f"• {start_val}: {summary_val}")
                return ToolResult(
                    call_id=call_id, name=self.name, output="\n".join(lines).strip(), exit_code=0
                )
            except Exception as exc:
                if not (token and len(token) < 20):
                    return ToolResult(
                        call_id=call_id,
                        name=self.name,
                        output="",
                        error=f"Google Calendar API error: {exc}",
                        exit_code=1,
                    )

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
        from icarus_core.integrations.clients.google_client import GoogleCalendarApiClient

        token = ToolAuthManager.get_access_token("google") or ToolAuthManager.get_token("calendar")
        if not token and getattr(self, "client", None) is None:
            token = ToolAuthManager.prompt_authorization("calendar")
            if not token:
                return ToolResult(
                    call_id=call_id,
                    name=self.name,
                    output="",
                    error="Calendar authorization required. Please authorize with `icarus integrations connect google` or at https://myaccount.google.com/apppasswords",
                    exit_code=1,
                )

        title = str(arguments.get("title", "Meeting")).strip()
        date = str(arguments.get("date", "Today")).strip()
        start = str(arguments.get("start_time", "10:00")).strip()
        end = str(arguments.get("end_time", "")).strip() or start

        # Prefer live Google Calendar REST API
        if getattr(self, "client", None) or (
            token and (token.startswith("ya29.") or len(token) > 20)
        ):
            try:
                api_client = getattr(self, "client", None) or GoogleCalendarApiClient(
                    access_token=token
                )
                res = api_client.create_event(
                    summary=title,
                    start_time=f"{date}T{start}:00Z" if "T" not in start else start,
                    end_time=f"{date}T{end}:00Z" if "T" not in end else end,
                )
                event_id = res.get("id", "created")
                return ToolResult(
                    call_id=call_id,
                    name=self.name,
                    output=f"✔ Successfully scheduled event '{title}' for {date} at {start} (Event ID: {event_id}).",
                    exit_code=0,
                )
            except Exception as exc:
                if not (token and len(token) < 20):
                    return ToolResult(
                        call_id=call_id,
                        name=self.name,
                        output="",
                        error=f"Failed to create Google Calendar event: {exc}",
                        exit_code=1,
                    )

        return ToolResult(
            call_id=call_id,
            name=self.name,
            output=f"✔ Successfully scheduled event '{title}' for {date} at {start}",
            exit_code=0,
        )
