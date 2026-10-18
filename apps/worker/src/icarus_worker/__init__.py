"""Autonomous background worker daemon and task scheduler for Icarus Agent."""

from icarus_worker.config import WorkerConfig, WorkerSettings
from icarus_worker.daemon import WorkerDaemon
from icarus_worker.handlers import (
    AgentRunJobHandler,
    HandlerRegistry,
    JobContext,
    JobHandler,
    NotificationJobHandler,
)

__version__ = "0.1.0"

__all__ = [
    "__version__",
    "AgentRunJobHandler",
    "HandlerRegistry",
    "JobContext",
    "JobHandler",
    "NotificationJobHandler",
    "WorkerConfig",
    "WorkerDaemon",
    "WorkerSettings",
]
