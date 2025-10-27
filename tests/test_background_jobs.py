from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest
from fakeredis import FakeRedis
from rq import SimpleWorker
from rq.job import JobStatus
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from projects.02-intermediate.app.core.jobs import (
    close_job_connection,
    enqueue_task_report,
    get_job_connection,
    get_job_queue,
    set_job_connection,
    set_job_session_factory,
)
from projects.02-intermediate.app.core.config import get_settings
from projects.02-intermediate.app.db.base import SQLModel
from projects.02-intermediate.app.models import TaskStatus, User, UserRole
from projects.02-intermediate.app.repositories import TaskReportRepository
from projects.02-intermediate.app.services import TaskReportService, TaskService

pytestmark = pytest.mark.asyncio


@pytest.fixture()
async def engine() -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest.fixture()
async def session(engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as db_session:
        yield db_session


@pytest.fixture()
async def user(session: AsyncSession) -> User:
    account = User(
        email="reporter@example.com",
        hashed_password="hashed",
        role=UserRole.USER,
    )
    session.add(account)
    await session.commit()
    await session.refresh(account)
    return account


@pytest.fixture(autouse=True)
async def configure_job_environment(engine: AsyncEngine) -> AsyncIterator[None]:
    fake = FakeRedis(decode_responses=False)
    set_job_connection(fake)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    @asynccontextmanager
    async def factory() -> AsyncIterator[AsyncSession]:
        async with session_factory() as db_session:
            yield db_session

    set_job_session_factory(factory)

    settings = get_settings()
    original_backoff = list(settings.job_retry_backoff_seconds)
    original_retries = settings.job_max_retries
    settings.job_retry_backoff_seconds = [0, 0, 0]
    settings.job_max_retries = 2
    try:
        yield
    finally:
        settings.job_retry_backoff_seconds = original_backoff
        settings.job_max_retries = original_retries
        set_job_session_factory(None)
        close_job_connection()


async def _create_tasks(session: AsyncSession, owner_id: int) -> None:
    service = TaskService(session)
    await service.create_task(owner_id=owner_id, title="Alpha", status=TaskStatus.PENDING)
    await service.create_task(owner_id=owner_id, title="Beta", status=TaskStatus.COMPLETED)


async def test_task_report_job_generates_summary(session: AsyncSession, user: User) -> None:
    assert user.id is not None
    await _create_tasks(session, user.id)

    job = enqueue_task_report(owner_id=user.id)

    worker = SimpleWorker([get_job_queue()], connection=get_job_connection())
    worker.work(burst=True, with_scheduler=True)

    repo = TaskReportRepository(session)
    report = await repo.get_by_owner(user.id)
    assert report is not None
    assert report.total_tasks == 2
    assert report.pending_tasks == 1
    assert report.completed_tasks == 1
    assert report.in_progress_tasks == 0
    assert report.cancelled_tasks == 0


async def test_task_report_job_is_idempotent(session: AsyncSession, user: User) -> None:
    assert user.id is not None
    await _create_tasks(session, user.id)

    worker = SimpleWorker([get_job_queue()], connection=get_job_connection())

    first_job = enqueue_task_report(owner_id=user.id)
    worker.work(burst=True, with_scheduler=True)

    repo = TaskReportRepository(session)
    first_report = await repo.get_by_owner(user.id)
    assert first_report is not None
    first_generated_at = first_report.generated_at

    await TaskService(session).create_task(owner_id=user.id, title="Gamma", status=TaskStatus.IN_PROGRESS)

    second_job = enqueue_task_report(owner_id=user.id)
    worker.work(burst=True, with_scheduler=True)

    second_report = await repo.get_by_owner(user.id)
    assert second_report is not None
    assert second_report.total_tasks == 3
    assert second_report.pending_tasks == 1
    assert second_report.in_progress_tasks == 1
    assert second_report.completed_tasks == 1
    assert second_report.generated_at >= first_generated_at
    assert first_job.id != second_job.id


async def test_task_report_job_retries_on_transient_failure(
    session: AsyncSession, user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert user.id is not None
    await _create_tasks(session, user.id)

    original_generate = TaskReportService.generate_report
    attempt_counter = {"count": 0}

    async def flaky_generate(self: TaskReportService, owner_id: int):  # type: ignore[override]
        attempt_counter["count"] += 1
        if attempt_counter["count"] < 3:
            raise RuntimeError("temporary failure")
        return await original_generate(self, owner_id)

    monkeypatch.setattr(TaskReportService, "generate_report", flaky_generate)

    job = enqueue_task_report(owner_id=user.id)
    worker = SimpleWorker([get_job_queue()], connection=get_job_connection())

    for _ in range(3):  # initial attempt + 2 retries
        worker.work(burst=True, with_scheduler=True)
        job.refresh()
        if job.get_status() == JobStatus.FINISHED:
            break
    else:
        pytest.fail("Job did not succeed after retries")

    assert attempt_counter["count"] == 3

    repo = TaskReportRepository(session)
    report = await repo.get_by_owner(user.id)
    assert report is not None
    assert report.total_tasks == 2

    assert job.get_status() == JobStatus.FINISHED
