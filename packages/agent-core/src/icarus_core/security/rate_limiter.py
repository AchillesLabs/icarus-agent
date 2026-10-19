"""High-throughput in-memory sliding-window rate limiter and active concurrency tracker."""

from __future__ import annotations

import contextlib
import math
import threading
import time
from collections import defaultdict, deque
from collections.abc import AsyncGenerator, Callable, Generator
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from icarus_contracts import RateLimitStatus


@dataclass(frozen=True)
class RateLimitResult:
    """Outcome of a rate limit evaluation."""

    allowed: bool
    limit: int
    remaining: int
    reset_seconds: int
    retry_after: int = 0

    def to_status(self) -> RateLimitStatus:
        """Convert result to a Pydantic RateLimitStatus contract."""
        from icarus_contracts import RateLimitStatus

        return RateLimitStatus(
            allowed=self.allowed,
            limit=self.limit,
            remaining=self.remaining,
            reset_seconds=self.reset_seconds,
            retry_after=self.retry_after,
        )


class SlidingWindowRateLimiter:
    """Thread-safe in-memory sliding-window rate limiter and execution concurrency tracker.

    Tracks request timestamps within a moving time window (default 60 seconds) and
    tracks active concurrent execution counts per tenant identity.
    """

    def __init__(
        self,
        default_rpm: int = 60,
        window_seconds: float = 60.0,
        max_concurrent_runs: int = 5,
        tenant_rpm_limits: dict[str, int] | None = None,
        tenant_concurrency_limits: dict[str, int] | None = None,
        time_func: Callable[[], float] = time.time,
    ) -> None:
        self.default_rpm = max(1, default_rpm)
        self.window_seconds = max(1.0, float(window_seconds))
        self.max_concurrent_runs = max(1, max_concurrent_runs)
        self.tenant_rpm_limits = dict(tenant_rpm_limits or {})
        self.tenant_concurrency_limits = dict(tenant_concurrency_limits or {})
        self.time_func = time_func

        self._lock = threading.Lock()
        self._windows: dict[str, deque[float]] = defaultdict(deque)
        self._active_runs: dict[str, int] = defaultdict(int)

    def get_rpm_limit(self, key: str) -> int:
        """Resolve the effective RPM limit for a given key."""
        if key in self.tenant_rpm_limits:
            return self.tenant_rpm_limits[key]
        if key.startswith("tenant:"):
            raw_id = key.split(":", 1)[1]
            if raw_id in self.tenant_rpm_limits:
                return self.tenant_rpm_limits[raw_id]
        return self.default_rpm

    def set_tenant_rpm_limit(self, tenant_id: str, rpm: int) -> None:
        """Configure a custom requests-per-minute limit for a specific tenant."""
        with self._lock:
            self.tenant_rpm_limits[tenant_id] = max(1, rpm)

    def get_concurrency_limit(self, key: str) -> int:
        """Resolve the maximum concurrent runs limit for a given key."""
        if key in self.tenant_concurrency_limits:
            return self.tenant_concurrency_limits[key]
        if key.startswith("tenant:"):
            raw_id = key.split(":", 1)[1]
            if raw_id in self.tenant_concurrency_limits:
                return self.tenant_concurrency_limits[raw_id]
        return self.max_concurrent_runs

    def set_tenant_concurrency_limit(self, tenant_id: str, limit: int) -> None:
        """Configure a custom concurrent runs limit for a specific tenant."""
        with self._lock:
            self.tenant_concurrency_limits[tenant_id] = max(1, limit)

    def check_rate_limit(self, key: str, cost: int = 1) -> RateLimitResult:
        """Evaluate whether a request costing `cost` units is allowed under the sliding window.

        If allowed, records the request timestamp and returns remaining capacity.
        If denied, returns allowed=False with the exact retry_after duration in seconds.
        """
        now = self.time_func()
        limit = self.get_rpm_limit(key)
        cutoff = now - self.window_seconds

        with self._lock:
            timestamps = self._windows[key]

            # Evict timestamps older than the moving window cutoff
            while timestamps and timestamps[0] <= cutoff:
                timestamps.popleft()

            current_count = len(timestamps)

            if current_count + cost <= limit:
                for _ in range(cost):
                    timestamps.append(now)
                remaining = max(0, limit - len(timestamps))
                oldest = timestamps[0] if timestamps else now
                reset_seconds = max(1, int(math.ceil(oldest + self.window_seconds - now)))
                return RateLimitResult(
                    allowed=True,
                    limit=limit,
                    remaining=remaining,
                    reset_seconds=reset_seconds,
                    retry_after=0,
                )
            else:
                oldest = timestamps[0] if timestamps else now
                retry_after = max(1, int(math.ceil(oldest + self.window_seconds - now)))
                return RateLimitResult(
                    allowed=False,
                    limit=limit,
                    remaining=0,
                    reset_seconds=retry_after,
                    retry_after=retry_after,
                )

    def acquire_concurrent_run(self, key: str) -> bool:
        """Attempt to acquire one execution concurrency slot for the given tenant key.

        Returns True if acquired under the concurrency ceiling, False if limit reached.
        """
        limit = self.get_concurrency_limit(key)
        with self._lock:
            current = self._active_runs[key]
            if current < limit:
                self._active_runs[key] = current + 1
                return True
            return False

    def release_concurrent_run(self, key: str) -> None:
        """Release one execution concurrency slot for the given tenant key."""
        with self._lock:
            current = self._active_runs.get(key, 0)
            if current > 0:
                self._active_runs[key] = current - 1
            if self._active_runs[key] == 0:
                self._active_runs.pop(key, None)

    def get_active_concurrent_runs(self, key: str) -> int:
        """Return the current number of active concurrent runs for the given tenant key."""
        with self._lock:
            return self._active_runs.get(key, 0)

    @contextlib.contextmanager
    def concurrency_scope(self, key: str) -> Generator[bool, None, None]:
        """Context manager attempting to acquire and reliably release a concurrency slot."""
        acquired = self.acquire_concurrent_run(key)
        try:
            yield acquired
        finally:
            if acquired:
                self.release_concurrent_run(key)

    @contextlib.asynccontextmanager
    async def async_concurrency_scope(self, key: str) -> AsyncGenerator[bool, None]:
        """Async context manager attempting to acquire and reliably release a concurrency slot."""
        acquired = self.acquire_concurrent_run(key)
        try:
            yield acquired
        finally:
            if acquired:
                self.release_concurrent_run(key)

    def reset(self, key: str | None = None) -> None:
        """Reset rate limit history and concurrency counts for a specific key or all keys."""
        with self._lock:
            if key is not None:
                self._windows.pop(key, None)
                self._active_runs.pop(key, None)
            else:
                self._windows.clear()
                self._active_runs.clear()
