from __future__ import annotations

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession
from importlib import import_module

BEGINNER_PACKAGE = "projects.01-beginner"


def load_beginner_module(path: str):
    return import_module(f"{BEGINNER_PACKAGE}.{path}")

models_module = load_beginner_module("app.models")
services_module = load_beginner_module("app.services")

TaskStatus = getattr(models_module, "TaskStatus")
TaskService = getattr(services_module, "TaskService")
UserService = getattr(services_module, "UserService")

pytestmark = pytest.mark.asyncio


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


async def test_user_service_update_missing_user_raises(session: AsyncSession) -> None:
    user_service = UserService(session)

    with pytest.raises(ValueError) as exc_info:
        await user_service.update_user(9999, full_name="Nope")
    assert "User 9999 does not exist" in str(exc_info.value)


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


async def test_task_creation_requires_valid_owner(session: AsyncSession) -> None:
    task_service = TaskService(session)

    with pytest.raises(ValueError):
        await task_service.create_task(owner_id=9999, title="Should fail")


async def test_task_update_for_owner_requires_ownership(session: AsyncSession) -> None:
    user_service = UserService(session)
    task_service = TaskService(session)

    owner = await user_service.create_user(
        email="owner@example.com",
        password="example-password",
        full_name="Owner",
    )
    other = await user_service.create_user(
        email="other@example.com",
        password="example-password",
        full_name="Other",
    )
    task = await task_service.create_task(owner_id=owner.id, title="Owner task")

    with pytest.raises(PermissionError):
        await task_service.update_task_for_owner(task.id, other.id, status=TaskStatus.CANCELLED)


async def test_task_delete_for_owner_requires_ownership(session: AsyncSession) -> None:
    user_service = UserService(session)
    task_service = TaskService(session)

    owner = await user_service.create_user(
        email="owner2@example.com",
        password="example-password",
        full_name="Owner Two",
    )
    other = await user_service.create_user(
        email="other2@example.com",
        password="example-password",
        full_name="Other Two",
    )
    task = await task_service.create_task(owner_id=owner.id, title="Owner task")

    with pytest.raises(PermissionError):
        await task_service.delete_task_for_owner(task.id, other.id)


async def test_task_delete_returns_false_when_missing(session: AsyncSession) -> None:
    task_service = TaskService(session)

    deleted = await task_service.delete_task(9999)
    assert deleted is False


async def test_reassign_task_requires_existing_owner(session: AsyncSession) -> None:
    user_service = UserService(session)
    task_service = TaskService(session)

    owner = await user_service.create_user(
        email="owner3@example.com",
        password="example-password",
        full_name="Owner Three",
    )
    task = await task_service.create_task(owner_id=owner.id, title="Reassign me")

    with pytest.raises(ValueError) as exc_info:
        await task_service.reassign_task(task.id, owner_id=12345)
    assert "Owner 12345 does not exist" in str(exc_info.value)
