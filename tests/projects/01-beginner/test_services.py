from __future__ import annotations

from collections.abc import AsyncIterator
from importlib import import_module

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

BEGINNER_PACKAGE = "projects.01-beginner"


def load_beginner_module(path: str):
    return import_module(f"{BEGINNER_PACKAGE}.{path}")


models_module = load_beginner_module("app.models")
services_module = load_beginner_module("app.services")

TaskStatus = getattr(models_module, "TaskStatus")
TaskService = getattr(services_module, "TaskService")
UserService = getattr(services_module, "UserService")


@pytest_asyncio.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def session(engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        try:
            yield session
        finally:
            transaction = session.in_transaction()
            if transaction is not None:
                await session.rollback()


@pytest.mark.asyncio
async def test_user_service_crud_flow(session: AsyncSession) -> None:
    user_service = UserService(session)

    created = await user_service.create_user(
        email="alice@example.com",
        password="example-password",
        full_name="Alice",
    )

    assert created.id is not None
    assert created.email == "alice@example.com"
    assert created.is_active is True

    fetched = await user_service.get_user(created.id)
    assert fetched is not None
    assert fetched.email == created.email

    by_email = await user_service.get_user_by_email("alice@example.com")
    assert by_email is not None
    assert by_email.id == created.id

    updated = await user_service.update_user(created.id, full_name="Alice Updated", is_active=False)
    assert updated.full_name == "Alice Updated"
    assert updated.is_active is False

    all_users = await user_service.list_users()
    assert len(all_users) == 1

    active_users = await user_service.list_active_users()
    assert active_users == []

    deleted = await user_service.delete_user(created.id)
    assert deleted is True
    assert await user_service.get_user(created.id) is None


@pytest.mark.asyncio
async def test_task_service_crud_flow(session: AsyncSession) -> None:
    user_service = UserService(session)
    task_service = TaskService(session)

    owner = await user_service.create_user(
        email="bob@example.com",
        password="example-password",
        full_name="Bob",
    )
    assert owner.id is not None

    task = await task_service.create_task(owner_id=owner.id, title="Write docs", description="Initial docs")
    assert task.id is not None
    assert task.status == TaskStatus.PENDING
    assert task.owner_id == owner.id

    owner_tasks = await task_service.list_tasks_for_owner(owner.id)
    assert len(owner_tasks) == 1

    status_tasks = await task_service.list_tasks_by_status(TaskStatus.PENDING)
    assert len(status_tasks) == 1

    updated = await task_service.update_task(
        task.id,
        status=TaskStatus.IN_PROGRESS,
        description="Updated docs",
    )
    assert updated.status == TaskStatus.IN_PROGRESS
    assert updated.description == "Updated docs"

    in_progress_tasks = await task_service.list_tasks_by_status(TaskStatus.IN_PROGRESS)
    assert len(in_progress_tasks) == 1

    other_user = await user_service.create_user(
        email="carol@example.com",
        password="example-password",
        full_name="Carol",
    )
    assert other_user.id is not None

    reassigned = await task_service.reassign_task(task.id, owner_id=other_user.id)
    assert reassigned.owner_id == other_user.id

    original_owner_tasks = await task_service.list_tasks_for_owner(owner.id)
    assert original_owner_tasks == []

    all_tasks = await task_service.list_tasks()
    assert len(all_tasks) == 1

    deleted = await task_service.delete_task(task.id)
    assert deleted is True
    assert await task_service.get_task(task.id) is None

    new_owner_tasks = await task_service.list_tasks_for_owner(other_user.id)
    assert new_owner_tasks == []


@pytest.mark.asyncio
async def test_task_creation_requires_valid_owner(session: AsyncSession) -> None:
    task_service = TaskService(session)

    with pytest.raises(ValueError):
        await task_service.create_task(owner_id=9999, title="Should fail")
