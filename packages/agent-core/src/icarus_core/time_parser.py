"""Natural language datetime parsing into UTC timestamps for reminders and scheduling."""

from __future__ import annotations

import re
from datetime import UTC, datetime, time, timedelta


def parse_natural_datetime(expression: str, now: datetime | None = None) -> datetime:
    """Parse relative or absolute natural language datetime expression into UTC datetime.

    Supported formats:
    - Relative offsets: 'in 2 hours', 'in 30 minutes', 'in 45 seconds', 'in 3 days', 'in 1 week'
    - Combined offsets: 'in 1 hour and 30 minutes', 'in 2 hours 15 mins'
    - Relative days: 'tomorrow at 9am', 'tomorrow at 15:30', 'today at 5pm', 'tomorrow'
    - Clocks: 'at 5pm', 'at 17:30', '9:00am'
    - ISO timestamps: '2026-10-25T14:30:00Z', '2026-10-25 09:00'
    """
    raw = expression.strip()
    if not raw:
        raise ValueError("Datetime expression cannot be empty.")

    current_time = now if now is not None else datetime.now(UTC)
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=UTC)

    lower = raw.lower()

    # 1. Try ISO formats first
    iso_result = _try_parse_iso(raw)
    if iso_result is not None:
        return iso_result

    # 2. Check for relative 'in ...' offsets
    if lower.startswith("in "):
        delta = _parse_relative_delta(lower[3:].strip())
        if delta is not None:
            return current_time + delta

    # 3. Check for 'tomorrow' / 'today' expressions
    day_result = _try_parse_relative_day(lower, current_time)
    if day_result is not None:
        return day_result

    # 4. Check for standalone clock times (e.g. 'at 5pm', 'at 17:30', '5pm')
    clock_result = _try_parse_clock_time(lower, current_time)
    if clock_result is not None:
        return clock_result

    raise ValueError(f"Could not parse datetime expression: '{expression}'.")


def _try_parse_iso(raw: str) -> datetime | None:
    """Attempt parsing standard ISO 8601 strings."""
    # Handle trailing Z
    clean = raw
    if clean.endswith("Z"):
        clean = clean[:-1] + "+00:00"

    for fmt in (
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%d %H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
    ):
        try:
            dt = datetime.strptime(clean, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=UTC)
            return dt.astimezone(UTC)
        except ValueError:
            continue
    return None


def _parse_relative_delta(delta_str: str) -> timedelta | None:
    """Parse string like '2 hours and 30 minutes', '45 mins', '1 day' into timedelta."""
    text = delta_str.replace("and", " ")
    matches = re.findall(r"(\d+(?:\.\d+)?)\s*([a-zA-Z]+)", text)
    if not matches:
        return None

    total_seconds = 0.0
    for value_str, unit in matches:
        try:
            val = float(value_str)
        except ValueError:
            return None

        u = unit.lower()
        if u in ("s", "sec", "secs", "second", "seconds"):
            total_seconds += val
        elif u in ("m", "min", "mins", "minute", "minutes"):
            total_seconds += val * 60.0
        elif u in ("h", "hr", "hrs", "hour", "hours"):
            total_seconds += val * 3600.0
        elif u in ("d", "day", "days"):
            total_seconds += val * 86400.0
        elif u in ("w", "wk", "wks", "week", "weeks"):
            total_seconds += val * 604800.0
        else:
            return None

    return timedelta(seconds=total_seconds) if total_seconds > 0 else None


def _try_parse_relative_day(text: str, current_time: datetime) -> datetime | None:
    """Parse 'tomorrow at 9am', 'today at 5pm', 'tomorrow'."""
    is_tomorrow = "tomorrow" in text
    is_today = "today" in text
    if not is_tomorrow and not is_today:
        return None

    # Base date
    target_date = (current_time + timedelta(days=1)).date() if is_tomorrow else current_time.date()

    # Extract time component after 'tomorrow' or 'today' (optional 'at')
    remainder = text.replace("tomorrow", "").replace("today", "").replace("at", "").strip()
    if not remainder:
        # Default to 09:00 AM
        return datetime.combine(target_date, time(hour=9, minute=0), tzinfo=UTC)

    parsed_time = _parse_time_component(remainder)
    if parsed_time is not None:
        return datetime.combine(target_date, parsed_time, tzinfo=UTC)

    return None


def _try_parse_clock_time(text: str, current_time: datetime) -> datetime | None:
    """Parse clock time expressions like 'at 5pm', 'at 17:30', '9am'."""
    clean = text.strip()
    if clean.startswith("at "):
        clean = clean[3:].strip()

    parsed_time = _parse_time_component(clean)
    if parsed_time is None:
        return None

    target_dt = datetime.combine(current_time.date(), parsed_time, tzinfo=UTC)
    # If the time has already passed today, roll over to tomorrow
    if target_dt <= current_time:
        target_dt += timedelta(days=1)
    return target_dt


def _parse_time_component(time_str: str) -> time | None:
    """Parse time string like '9am', '5:30pm', '14:00', '9:30'."""
    raw = time_str.strip().lower()

    # Match '9am', '9:30am', '11pm', '11:45pm'
    am_pm_match = re.match(r"^(\d{1,2})(?::(\d{2}))?\s*(am|pm)$", raw)
    if am_pm_match:
        hour = int(am_pm_match.group(1))
        minute = int(am_pm_match.group(2) or 0)
        period = am_pm_match.group(3)

        if hour > 12 or minute > 59:
            return None

        if period == "pm" and hour != 12:
            hour += 12
        elif period == "am" and hour == 12:
            hour = 0
        return time(hour=hour, minute=minute)

    # Match 24-hour time '14:30', '09:00', '9:30'
    mil_match = re.match(r"^(\d{1,2}):(\d{2})(?::(\d{2}))?$", raw)
    if mil_match:
        hour = int(mil_match.group(1))
        minute = int(mil_match.group(2))
        second = int(mil_match.group(3) or 0)
        if 0 <= hour <= 23 and 0 <= minute <= 59 and 0 <= second <= 59:
            return time(hour=hour, minute=minute, second=second)

    return None
