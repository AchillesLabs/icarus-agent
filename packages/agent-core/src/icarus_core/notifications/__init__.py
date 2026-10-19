"""Notifications module for Icarus Agent."""

from __future__ import annotations

from icarus_core.notifications.desktop import (
    send_desktop_notification,
    set_notification_sender,
)

__all__ = [
    "send_desktop_notification",
    "set_notification_sender",
]
