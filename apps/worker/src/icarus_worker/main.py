"""Main entrypoint for icarus-worker process."""

import asyncio
import contextlib
import logging
import sys

from icarus_worker.config import WorkerSettings
from icarus_worker.daemon import WorkerDaemon


def main() -> None:
    """Initialize logging, configure settings, and run the worker daemon."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stdout,
    )
    settings = WorkerSettings()
    daemon = WorkerDaemon(settings=settings)
    with contextlib.suppress(KeyboardInterrupt, SystemExit):
        asyncio.run(daemon.run_forever())


if __name__ == "__main__":
    main()
