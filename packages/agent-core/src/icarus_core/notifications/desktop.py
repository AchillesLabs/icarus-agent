"""Cross-platform desktop notification emitter for background tasks and reminders."""

from __future__ import annotations

import logging
import platform
import shutil
import subprocess
from collections.abc import Callable

logger = logging.getLogger("icarus.notifications")

# Global override for testing and custom delivery
_custom_sender: Callable[[str, str], bool] | None = None


def set_notification_sender(sender: Callable[[str, str], bool] | None) -> None:
    """Override notification sender with a custom callback (e.g. for testing)."""
    global _custom_sender
    _custom_sender = sender


def send_desktop_notification(title: str, message: str) -> bool:
    """Emit a native desktop notification across Windows, macOS, and Linux platforms."""
    global _custom_sender
    if _custom_sender is not None:
        try:
            return _custom_sender(title, message)
        except Exception as exc:
            logger.warning("Custom notification sender failed: %s", exc)
            return False

    system = platform.system().lower()
    try:
        if system == "windows":
            return _send_windows_notification(title, message)
        elif system == "darwin":
            return _send_macos_notification(title, message)
        elif system == "linux":
            return _send_linux_notification(title, message)
        else:
            logger.info("Notification on %s: [%s] %s", system, title, message)
            return True
    except Exception as exc:
        logger.warning("Failed to emit desktop notification on %s: %s", system, exc)
        return False


def _send_windows_notification(title: str, message: str) -> bool:
    """Emit Windows notification via PowerShell."""
    clean_title = title.replace('"', '`"').replace("'", "''")
    clean_msg = message.replace('"', '`"').replace("'", "''")

    ps_script = (
        "[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null;"
        "$template = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02);"
        "$strings = $template.GetElementsByTagName('text');"
        f"$strings[0].AppendChild($template.CreateTextNode('{clean_title}')) | Out-Null;"
        f"$strings[1].AppendChild($template.CreateTextNode('{clean_msg}')) | Out-Null;"
        "$toast = [Windows.UI.Notifications.ToastNotification]::new($template);"
        "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('Icarus Agent').Show($toast);"
    )

    try:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_script],
            capture_output=True,
            timeout=5.0,
            check=False,
        )
        return proc.returncode == 0
    except Exception as exc:
        logger.debug("PowerShell toast notification fallback: %s", exc)
        return False


def _send_macos_notification(title: str, message: str) -> bool:
    """Emit macOS notification via AppleScript."""
    clean_title = title.replace('"', '\\"')
    clean_msg = message.replace('"', '\\"')
    script = f'display notification "{clean_msg}" with title "{clean_title}"'
    proc = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True,
        timeout=5.0,
        check=False,
    )
    return proc.returncode == 0


def _send_linux_notification(title: str, message: str) -> bool:
    """Emit Linux notification via notify-send."""
    if not shutil.which("notify-send"):
        logger.info("notify-send not found on system: [%s] %s", title, message)
        return False

    proc = subprocess.run(
        ["notify-send", title, message],
        capture_output=True,
        timeout=5.0,
        check=False,
    )
    return proc.returncode == 0
