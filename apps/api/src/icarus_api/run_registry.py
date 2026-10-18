"""In-memory registry of active executing agent runs and their asyncio tasks."""

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ActiveRun:
    """Metadata and execution handle for a currently executing agent run."""

    run_id: str
    owner_id: str
    task: asyncio.Task[Any]
    started_at: float = field(default_factory=time.monotonic)


class ActiveRunRegistry:
    """Thread-safe and async-safe in-memory registry of active agent runs."""

    def __init__(self) -> None:
        self._runs: dict[str, ActiveRun] = {}
        self._lock = asyncio.Lock()

    async def register(self, run_id: str, owner_id: str, task: asyncio.Task[Any]) -> None:
        """Register an active run task."""
        async with self._lock:
            self._runs[run_id] = ActiveRun(run_id=run_id, owner_id=owner_id, task=task)

    async def unregister(self, run_id: str) -> None:
        """Unregister a completed or cancelled run."""
        async with self._lock:
            self._runs.pop(run_id, None)

    async def get(self, run_id: str, owner_id: str | None = None) -> ActiveRun | None:
        """Retrieve an active run, optionally enforcing tenant ownership."""
        async with self._lock:
            run = self._runs.get(run_id)
            if run is None:
                return None
            if owner_id is not None and run.owner_id != owner_id:
                return None
            return run

    async def cancel(self, run_id: str, owner_id: str) -> bool:
        """Signal cancellation to an active run task if owned by owner_id."""
        async with self._lock:
            run = self._runs.get(run_id)
            if run is None or run.owner_id != owner_id:
                return False
            if not run.task.done():
                run.task.cancel()
            return True

    async def list_active(self, owner_id: str | None = None) -> list[ActiveRun]:
        """List active runs, optionally filtered by tenant owner."""
        async with self._lock:
            if owner_id is None:
                return list(self._runs.values())
            return [r for r in self._runs.values() if r.owner_id == owner_id]
