"""Entry point for running the background job worker."""

from __future__ import annotations

import logging

from rq import Connection, Worker

from .core.config import get_settings
from .core.jobs import get_job_connection, get_job_queue

logger = logging.getLogger("projects.02-intermediate.app.worker")


def run() -> None:
    """Start an RQ worker bound to the configured queue."""

    settings = get_settings()
    connection = get_job_connection()
    queue = get_job_queue()

    worker_name = settings.job_worker_name or None

    logger.info(
        "Starting RQ worker '%s' listening on queue '%s'", worker_name or "anonymous", queue.name
    )
    with Connection(connection):
        worker = Worker([queue], name=worker_name)
        worker.work(with_scheduler=True)


if __name__ == "__main__":  # pragma: no cover - script entry point
    run()
