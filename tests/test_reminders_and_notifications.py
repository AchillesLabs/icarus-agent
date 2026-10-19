"""Unit and integration tests for natural language reminders and desktop notifications."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from icarus_contracts.jobs import ScheduledJobCreate, ScheduledJobStatus
from icarus_core.notifications.desktop import (
    send_desktop_notification,
    set_notification_sender,
)
from icarus_core.persistence.database import DatabaseManager
from icarus_core.persistence.models import Base
from icarus_core.persistence.repository import ScheduledJobRepository
from icarus_core.time_parser import parse_natural_datetime
from icarus_core.tools.registry import create_default_registry
from icarus_core.tools.reminders import ListRemindersTool, ScheduleReminderTool, format_timedelta
from icarus_worker.daemon import WorkerDaemon
from icarus_worker.handlers import JobContext, NotificationJobHandler


@pytest.fixture
def test_db_manager(tmp_path: Path) -> DatabaseManager:
    """Provide an isolated SQLite database manager."""
    db_file = tmp_path / "test_reminders.db"
    db_url = f"sqlite:///{db_file.as_posix()}"
    mgr = DatabaseManager(db_url=db_url)
    Base.metadata.create_all(mgr.engine)
    return mgr


def test_time_parser_relative_offsets():
    """Verify relative natural language parsing."""
    fixed_now = datetime(2026, 10, 20, 12, 0, 0, tzinfo=UTC)

    # Minutes
    t1 = parse_natural_datetime("in 30 minutes", now=fixed_now)
    assert t1 == fixed_now + timedelta(minutes=30)

    t2 = parse_natural_datetime("in 15 mins", now=fixed_now)
    assert t2 == fixed_now + timedelta(minutes=15)

    # Hours
    t3 = parse_natural_datetime("in 2 hours", now=fixed_now)
    assert t3 == fixed_now + timedelta(hours=2)

    # Combined
    t4 = parse_natural_datetime("in 1 hour and 30 minutes", now=fixed_now)
    assert t4 == fixed_now + timedelta(hours=1, minutes=30)

    # Days and weeks
    t5 = parse_natural_datetime("in 3 days", now=fixed_now)
    assert t5 == fixed_now + timedelta(days=3)

    t6 = parse_natural_datetime("in 1 week", now=fixed_now)
    assert t6 == fixed_now + timedelta(days=7)

    # Seconds
    t7 = parse_natural_datetime("in 45 seconds", now=fixed_now)
    assert t7 == fixed_now + timedelta(seconds=45)


def test_time_parser_relative_days_and_clocks():
    """Verify 'tomorrow', 'today', and clock times."""
    fixed_now = datetime(2026, 10, 20, 10, 0, 0, tzinfo=UTC)

    # Tomorrow with specific time
    t1 = parse_natural_datetime("tomorrow at 9am", now=fixed_now)
    assert t1 == datetime(2026, 10, 21, 9, 0, 0, tzinfo=UTC)

    t2 = parse_natural_datetime("tomorrow at 15:30", now=fixed_now)
    assert t2 == datetime(2026, 10, 21, 15, 30, 0, tzinfo=UTC)

    # Tomorrow default
    t3 = parse_natural_datetime("tomorrow", now=fixed_now)
    assert t3 == datetime(2026, 10, 21, 9, 0, 0, tzinfo=UTC)

    # Today at time in future
    t4 = parse_natural_datetime("today at 5pm", now=fixed_now)
    assert t4 == datetime(2026, 10, 20, 17, 0, 0, tzinfo=UTC)

    # Standalone clock later today
    t5 = parse_natural_datetime("at 2pm", now=fixed_now)
    assert t5 == datetime(2026, 10, 20, 14, 0, 0, tzinfo=UTC)

    # Standalone clock earlier today rolls over to tomorrow
    t6 = parse_natural_datetime("at 8am", now=fixed_now)
    assert t6 == datetime(2026, 10, 21, 8, 0, 0, tzinfo=UTC)


def test_time_parser_iso_and_errors():
    """Verify ISO parsing and invalid syntax rejection."""
    iso_str = "2026-10-25T14:30:00Z"
    t1 = parse_natural_datetime(iso_str)
    assert t1 == datetime(2026, 10, 25, 14, 30, 0, tzinfo=UTC)

    with pytest.raises(ValueError, match="expression cannot be empty"):
        parse_natural_datetime("  ")

    with pytest.raises(ValueError, match="Could not parse datetime expression"):
        parse_natural_datetime("unparseable gibberish 1234")


def test_format_timedelta():
    """Verify human readable timedelta formatting."""
    now = datetime(2026, 10, 20, 10, 0, 0, tzinfo=UTC)
    t1 = now + timedelta(hours=2, minutes=15)
    assert format_timedelta(t1, now) == "2h 15m"

    t2 = now + timedelta(days=2, hours=3)
    assert format_timedelta(t2, now) == "2d 3h"

    t3 = now + timedelta(seconds=25)
    assert format_timedelta(t3, now) == "25s"

    t4 = now - timedelta(minutes=5)
    assert format_timedelta(t4, now) == "due now"


def test_desktop_notifications_custom_sender():
    """Verify desktop notification dispatch through custom callback."""
    emitted: list[tuple[str, str]] = []

    def mock_sender(title: str, msg: str) -> bool:
        emitted.append((title, msg))
        return True

    set_notification_sender(mock_sender)
    try:
        ok = send_desktop_notification("Test Alert", "Flight price dropped to $450")
        assert ok is True
        assert len(emitted) == 1
        assert emitted[0] == ("Test Alert", "Flight price dropped to $450")
    finally:
        set_notification_sender(None)


def test_schedule_and_list_reminders_tools(test_db_manager: DatabaseManager):
    """Test full conversational scheduling and query cycle using tools."""
    schedule_tool = ScheduleReminderTool(db_manager=test_db_manager)
    list_tool = ListRemindersTool(db_manager=test_db_manager)

    assert schedule_tool.name == "schedule_reminder"
    assert list_tool.name == "list_reminders"

    # 1. Schedule reminder
    res = schedule_tool.execute(
        arguments={
            "message": "Check flight prices to Tokyo",
            "time": "in 2 hours",
        },
        workspace_root=".",
    )
    assert res.exit_code == 0
    assert "Successfully scheduled reminder" in res.output
    assert "Check flight prices to Tokyo" in res.output

    # 2. List reminders (pending)
    list_res = list_tool.execute(arguments={"status": "pending"}, workspace_root=".")
    assert list_res.exit_code == 0
    assert "Found 1 reminder(s)" in list_res.output
    assert "Check flight prices to Tokyo" in list_res.output

    # 3. Schedule another reminder
    res2 = schedule_tool.execute(
        arguments={
            "message": "Submit quarterly report",
            "time": "tomorrow at 9am",
        },
        workspace_root=".",
    )
    assert res2.exit_code == 0

    list_res2 = list_tool.execute(arguments={"status": "all"}, workspace_root=".")
    assert "Found 2 reminder(s)" in list_res2.output

    # 4. Error validation: missing message
    bad_res1 = schedule_tool.execute(
        arguments={"message": "", "time": "in 1 hour"}, workspace_root="."
    )
    assert bad_res1.exit_code == 1
    assert "Parameter 'message' cannot be empty" in bad_res1.error

    # 5. Error validation: past time
    bad_res2 = schedule_tool.execute(
        arguments={"message": "Old task", "time": "2020-01-01"}, workspace_root="."
    )
    assert bad_res2.exit_code == 1
    assert "must be in the future" in bad_res2.error


@pytest.mark.asyncio
async def test_worker_notification_handler_integration(test_db_manager: DatabaseManager):
    """Verify worker NotificationJobHandler claims reminder and emits notification."""
    notifs: list[tuple[str, str]] = []

    def mock_notifier(title: str, msg: str) -> bool:
        notifs.append((title, msg))
        return True

    set_notification_sender(mock_notifier)
    try:
        repo = ScheduledJobRepository(test_db_manager)
        now = datetime.now(UTC)
        job = repo.create_job(
            ScheduledJobCreate(
                job_type="reminder",
                scheduled_at=now - timedelta(seconds=1),  # Eligible for claiming
                payload={"message": "Drink water", "channel": "desktop"},
                owner_id="default",
            )
        )

        handler = NotificationJobHandler()
        context = JobContext(
            worker_id="test-worker-1",
            db_manager=test_db_manager,
            settings=None,  # type: ignore[arg-type]
        )

        result = await handler.handle(job, context)
        assert result is not None
        assert result["status"] == "delivered"
        assert result["desktop_notified"] is True
        assert result["message"] == "Drink water"

        assert len(notifs) == 1
        assert notifs[0] == ("Icarus Reminder", "Drink water")
    finally:
        set_notification_sender(None)


def test_registry_includes_reminder_tools():
    """Verify create_default_registry includes ScheduleReminderTool and ListRemindersTool."""
    registry = create_default_registry(load_mcp=False)
    assert registry.has("schedule_reminder")
    assert registry.has("list_reminders")
    assert registry.has("web_search")
    assert registry.has("fetch_webpage")
