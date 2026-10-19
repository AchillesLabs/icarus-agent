"""Worker daemon process polling, atomically claiming, and executing scheduled jobs."""

import asyncio
import contextlib
import logging
import signal
from typing import Any

from icarus_contracts import ScheduledJobDTO
from icarus_core.persistence.database import DatabaseManager
from icarus_core.persistence.repository import ScheduledJobRepository
from icarus_core.providers import ProviderRegistry
from icarus_core.security import CredentialVault

from icarus_worker.config import WorkerSettings
from icarus_worker.handlers import HandlerRegistry, JobContext

logger = logging.getLogger("icarus.worker")


class WorkerDaemon:
    """Autonomous async daemon polling and executing scheduled background jobs."""

    def __init__(
        self,
        settings: WorkerSettings | None = None,
        db_manager: DatabaseManager | None = None,
        handler_registry: HandlerRegistry | None = None,
        vault: CredentialVault | None = None,
        provider_registry: ProviderRegistry | None = None,
    ) -> None:
        self.settings = settings or WorkerSettings()
        self.db_manager = db_manager or DatabaseManager(db_url=self.settings.database_url)
        self.handler_registry = handler_registry or HandlerRegistry.default_registry()
        self.job_repo = ScheduledJobRepository(self.db_manager)
        self.vault = vault or CredentialVault()
        self.provider_registry = provider_registry

        self._stop_event = asyncio.Event()
        self._is_running = False

        # Metrics & diagnostics
        self.jobs_processed = 0
        self.jobs_failed = 0
        self.jobs_retried = 0

    @property
    def is_running(self) -> bool:
        """Return True if daemon loop is actively running."""
        return self._is_running

    @property
    def context(self) -> JobContext:
        """Return a fresh JobContext instance for handler dispatch."""
        return JobContext(
            worker_id=self.settings.worker_id,
            db_manager=self.db_manager,
            settings=self.settings,
            vault=self.vault,
            provider_registry=self.provider_registry,
        )

    async def run_once(self) -> ScheduledJobDTO | None:
        """Attempt to claim and process a single eligible pending or orphaned scheduled job."""
        job = self.job_repo.claim_next_job(
            worker_id=self.settings.worker_id,
            lease_duration_seconds=self.settings.lease_duration_seconds,
        )
        if job is None:
            return None

        logger.info(
            "Claimed scheduled job %s (type=%s, owner=%s) by worker %s",
            job.id,
            job.job_type,
            job.owner_id,
            self.settings.worker_id,
        )

        handler = self.handler_registry.get(job.job_type)
        if handler is None:
            err_msg = f"No handler registered for job type '{job.job_type}'"
            logger.error("Job %s failed: %s", job.id, err_msg)
            self.job_repo.fail_job(
                job.id,
                error_message=err_msg,
                retry=False,
                owner_id=job.owner_id,
            )
            self.jobs_failed += 1
            return self.job_repo.get_job(job.id, owner_id=job.owner_id)

        try:
            result = await handler.handle(job, self.context)
            if result is not None:
                new_payload: dict[str, Any] = dict(job.payload or {})
                new_payload["result"] = result
                self.job_repo.update_job(job.id, payload=new_payload, owner_id=job.owner_id)

            completed = self.job_repo.complete_job(job.id, owner_id=job.owner_id)
            self.jobs_processed += 1
            logger.info("Successfully completed job %s", job.id)
            return completed
        except Exception as exc:
            err_msg = str(exc) or type(exc).__name__
            payload = job.payload or {}
            max_retries = int(payload.get("max_retries", self.settings.max_retries))
            next_retry = job.retry_count + 1
            should_retry = next_retry < max_retries

            delay_seconds = self.settings.retry_backoff_base_seconds * (2**job.retry_count)
            logger.warning(
                "Execution of job %s failed (retry %d/%d, should_retry=%s): %s",
                job.id,
                next_retry,
                max_retries,
                should_retry,
                err_msg,
            )

            updated = self.job_repo.fail_job(
                job.id,
                error_message=err_msg,
                retry=should_retry,
                retry_delay_seconds=delay_seconds,
                owner_id=job.owner_id,
            )
            if should_retry:
                self.jobs_retried += 1
            else:
                self.jobs_failed += 1
            return updated

    async def run_forever(self) -> None:
        """Run the daemon polling loop continuously until stop() is called."""
        self._is_running = True
        self._stop_event.clear()
        self._setup_signals()

        logger.info(
            "Worker daemon started (id=%s, poll_interval=%.2fs, max_backoff=%.2fs)",
            self.settings.worker_id,
            self.settings.poll_interval_seconds,
            self.settings.poll_max_backoff_seconds,
        )

        current_interval = self.settings.poll_interval_seconds
        try:
            while not self._stop_event.is_set():
                try:
                    job = await self.run_once()
                    if job is not None:
                        # Job processed: reset interval and immediately check for next
                        current_interval = self.settings.poll_interval_seconds
                        continue
                    else:
                        # Idle: apply backoff
                        current_interval = min(
                            current_interval * 1.5,
                            self.settings.poll_max_backoff_seconds,
                        )
                except Exception as exc:
                    logger.error("Unexpected error in worker loop: %s", exc, exc_info=True)
                    current_interval = self.settings.poll_interval_seconds

                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(self._stop_event.wait(), timeout=current_interval)
        finally:
            self._is_running = False
            logger.info("Worker daemon stopped (id=%s)", self.settings.worker_id)

    def stop(self) -> None:
        """Signal the daemon to stop processing and exit gracefully."""
        logger.info("Stopping worker daemon (id=%s)...", self.settings.worker_id)
        self._stop_event.set()

    def _setup_signals(self) -> None:
        """Attach SIGINT and SIGTERM handlers when running in the main thread."""
        with contextlib.suppress(RuntimeError):
            loop = asyncio.get_running_loop()
            for sig in (signal.SIGINT, signal.SIGTERM):
                with contextlib.suppress(NotImplementedError, RuntimeError):
                    loop.add_signal_handler(sig, self.stop)
