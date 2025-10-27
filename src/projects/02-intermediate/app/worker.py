"""Entry point for running the background job worker."""

from __future__ import annotations

import logging

from rq import Connection, Worker

from .core.config import get_settings
from .core.jobs import get_job_connection, get_job_queue
from .core.logging import configure_logging

logger = logging.getLogger("projects.02-intermediate.app.worker")


def run() -> None:
    """Start an RQ worker bound to the configured queue."""

    settings = get_settings()
    configure_logging(settings)

    connection = get_job_connection()
    queue = get_job_queue()

    worker_name = settings.job_worker_name or None

    logger.info(
        "Starting RQ worker '%s' listening on queue '%s'",
        worker_name or "anonymous",
        queue.name,
        extra={"queue": queue.name, "worker_name": worker_name or "anonymous"},
    )
    with Connection(connection):
        worker = Worker([queue], name=worker_name)
        worker.work(with_scheduler=True)


if __name__ == "__main__":  # pragma: no cover - script entry point
    run()
