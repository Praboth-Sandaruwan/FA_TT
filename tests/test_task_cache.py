from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from fakeredis.aioredis import FakeRedis
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from projects.02-intermediate.app.api.routers.tasks import get_task_statistics, list_tasks
from projects.02-intermediate.app.core.cache import cache_metrics, close_cache_client, set_cache_client
from projects.02-intermediate.app.core.config import get_settings
from projects.02-intermediate.app.db.base import SQLModel
from projects.02-intermediate.app.models import TaskStatus, User, UserRole
from projects.02-intermediate.app.services import TaskService

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
async def configure_cache() -> AsyncIterator[None]:
    fake = FakeRedis(decode_responses=True)
    set_cache_client(fake)
    cache_metrics.reset()
    settings = get_settings()
    settings.cache_enabled = True
    try:
        yield
    finally:
        await close_cache_client()
        cache_metrics.reset()


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
        email="user@example.com",
        hashed_password="hashed",
        role=UserRole.USER,
    )
    session.add(account)
    await session.commit()
    await session.refresh(account)
    return account


async def test_task_list_cache_hit_miss_and_invalidation(session: AsyncSession, user: User) -> None:
    service = TaskService(session)
    assert user.id is not None
    owner_id = user.id
    await service.create_task(owner_id=owner_id, title="Task 1")
    await service.create_task(owner_id=owner_id, title="Task 2")

    cache_metrics.reset()

    first = await list_tasks(session=session, current_user=user)
    assert first.total == 2
    metrics = cache_metrics.snapshot()
    assert metrics["misses"] == 1
    assert metrics["hits"] == 0
    assert metrics["skipped"] == 0

    second = await list_tasks(session=session, current_user=user)
    metrics = cache_metrics.snapshot()
    assert metrics["hits"] == 1
    assert metrics["misses"] == 1
    assert second.total == first.total

    await service.create_task(owner_id=owner_id, title="Task 3")

    third = await list_tasks(session=session, current_user=user)
    metrics = cache_metrics.snapshot()
    assert metrics["misses"] == 2
    assert metrics["hits"] == 1
    assert metrics["invalidations"] >= 1
    assert third.total == 3


async def test_task_statistics_cache_refreshes_after_update(session: AsyncSession, user: User) -> None:
    service = TaskService(session)
    assert user.id is not None
    owner_id = user.id
    completed = await service.create_task(
        owner_id=owner_id,
        title="Completed",
        status=TaskStatus.COMPLETED,
    )
    await service.create_task(owner_id=owner_id, title="Pending", status=TaskStatus.PENDING)

    cache_metrics.reset()

    initial = await get_task_statistics(session=session, current_user=user)
    assert initial.owner_id == owner_id
    assert initial.total == 2
    assert initial.by_status[TaskStatus.COMPLETED.value] == 1
    assert initial.by_status[TaskStatus.PENDING.value] == 1
    metrics = cache_metrics.snapshot()
    assert metrics["misses"] == 1
    assert metrics["hits"] == 0

    cached = await get_task_statistics(session=session, current_user=user)
    metrics = cache_metrics.snapshot()
    assert metrics["hits"] == 1
    assert metrics["misses"] == 1
    assert cached.by_status == initial.by_status

    assert completed.id is not None
    await service.update_task(completed.id, status=TaskStatus.IN_PROGRESS)

    refreshed = await get_task_statistics(session=session, current_user=user)
    metrics = cache_metrics.snapshot()
    assert metrics["misses"] == 2
    assert metrics["hits"] == 1
    assert metrics["invalidations"] >= 1
    assert refreshed.total == 2
    assert refreshed.by_status[TaskStatus.IN_PROGRESS.value] == 1
    assert refreshed.by_status[TaskStatus.COMPLETED.value] == 0
