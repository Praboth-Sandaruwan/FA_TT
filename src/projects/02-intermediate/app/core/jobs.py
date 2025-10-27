"""RQ integration helpers for the intermediate application."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from threading import Lock
from typing import TypeVar
from uuid import uuid4

from redis import Redis
from redis.exceptions import RedisError
from rq import Queue
from rq.job import Job, Retry

from .config import get_settings

logger = logging.getLogger("projects.02-intermediate.app.core.jobs")

T = TypeVar("T")

_job_connection: Redis | None = None
_job_queue: Queue | None = None
_job_lock = Lock()
_job_session_factory: Callable[[], AbstractAsyncContextManager["AsyncSession"]] | None = None


class JobQueueUnavailableError(RuntimeError):
    """Raised when the Redis-backed job queue cannot be reached."""


def set_job_connection(connection: Redis | None) -> None:
    """Inject a Redis connection for job queue operations (primarily for tests)."""

    global _job_connection, _job_queue
    with _job_lock:
        _job_connection = connection
        _job_queue = None


def close_job_connection() -> None:
    """Close the active Redis connection if one exists."""

    global _job_connection, _job_queue
    with _job_lock:
        connection = _job_connection
        if connection is not None:
            try:
                connection.close()
            except Exception:  # pragma: no cover - closing failures are best-effort
                logger.debug("Failed to close Redis connection cleanly.", exc_info=True)
        _job_connection = None
        _job_queue = None


def set_job_session_factory(
    factory: Callable[[], AbstractAsyncContextManager["AsyncSession"]] | None,
) -> None:
    """Override the session factory used when executing jobs."""

    global _job_session_factory
    with _job_lock:
        _job_session_factory = factory


@asynccontextmanager
async def _default_job_session_factory() -> AsyncIterator["AsyncSession"]:
    from ..db.session import async_session_maker  # Local import to avoid circular dependency

    async with async_session_maker() as session:
        yield session


async def execute_in_job_session(
    callback: Callable[["AsyncSession"], Awaitable[T]],
) -> T:
    """Execute a coroutine with a managed database session for job processing."""

    factory = _job_session_factory or _default_job_session_factory
    async with factory() as session:
        return await callback(session)


def _resolve_job_connection() -> Redis:
    global _job_connection
    with _job_lock:
        if _job_connection is not None:
            return _job_connection
        settings = get_settings()
        try:
            connection = Redis.from_url(settings.redis_url)
            connection.ping()
        except RedisError as exc:  # pragma: no cover - network failures
            logger.error("Redis job queue unavailable.", exc_info=True)
            raise JobQueueUnavailableError("Job queue is unavailable.") from exc
        else:
            _job_connection = connection
            return connection


def _resolve_job_queue() -> Queue:
    global _job_queue
    with _job_lock:
        if _job_queue is not None:
            return _job_queue
        connection = _resolve_job_connection()
        settings = get_settings()
        timeout = settings.job_default_timeout or None
        queue = Queue(settings.job_queue_name, connection=connection, default_timeout=timeout)
        _job_queue = queue
        return queue


def get_job_connection() -> Redis:
    """Return the Redis connection used for job processing."""

    return _resolve_job_connection()


def get_job_queue() -> Queue:
    """Return the job queue configured for the application."""

    return _resolve_job_queue()


def enqueue_task_report(owner_id: int, *, request_id: str | None = None) -> Job:
    """Enqueue a task report generation job for the supplied owner."""

    from ..jobs.reporting import generate_task_report_job

    queue = _resolve_job_queue()
    settings = get_settings()
    job_id = request_id or f"task-report:{owner_id}:{uuid4()}"
    retry: Retry | None = None
    if settings.job_max_retries > 0:
        intervals = settings.job_retry_backoff_seconds or [0]
        retry = Retry(max=settings.job_max_retries, interval=intervals)
    result_ttl = settings.job_result_ttl_seconds or None
    timeout = settings.job_default_timeout or None
    try:
        job = queue.enqueue(
            generate_task_report_job,
            owner_id,
            job_id=job_id,
            retry=retry,
            result_ttl=result_ttl,
            failure_ttl=result_ttl,
            description=f"Generate task report for owner {owner_id}",
            timeout=timeout,
        )
    except RedisError as exc:  # pragma: no cover - network failures
        logger.error("Failed to enqueue task report job for owner %s", owner_id, exc_info=True)
        raise JobQueueUnavailableError("Unable to enqueue job; Redis is unavailable.") from exc
    logger.info("Enqueued task report job %s for owner %s", job.id, owner_id)
    return job


__all__ = [
    "JobQueueUnavailableError",
    "close_job_connection",
    "enqueue_task_report",
    "execute_in_job_session",
    "get_job_connection",
    "get_job_queue",
    "set_job_connection",
    "set_job_session_factory",
]
