from __future__ import annotations

from collections.abc import AsyncIterator
import asyncio

import pytest
from fastapi.security import OAuth2PasswordRequestForm
from mongomock_motor import AsyncMongoMockClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from projects.02-intermediate.app.activity import (
    ActivityAction,
    ActivityLogService,
    ActivityEvent,
    close_activity_store,
    get_activity_collection,
    init_activity_store,
)
from projects.02-intermediate.app.api.routers.auth import login
from projects.02-intermediate.app.api.routers.tasks import create_task, update_task
from projects.02-intermediate.app.core.config import get_settings
from projects.02-intermediate.app.db.base import SQLModel
from projects.02-intermediate.app.models import TaskStatus, User
from projects.02-intermediate.app.schemas import TaskCreate, TaskUpdate
from projects.02-intermediate.app.services import UserService

pytestmark = pytest.mark.asyncio


@pytest.fixture()
async def activity_store() -> AsyncIterator[None]:
    client = AsyncMongoMockClient()
    settings = get_settings()
    settings.mongo_database = "intermediate_activity_test"
    settings.activity_ttl_seconds = 300
    await init_activity_store(client=client, force=True)
    try:
        yield
    finally:
        await close_activity_store()


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
    service = UserService(session)
    account = await service.create_user(email="user@example.com", password="secret", full_name="Test User")
    assert account.id is not None
    return account


async def test_ttl_index_respects_settings() -> None:
    client = AsyncMongoMockClient()
    settings = get_settings()
    settings.mongo_database = "intermediate_activity_test_ttl"
    settings.activity_ttl_seconds = 864
    await init_activity_store(client=client, force=True)
    collection = get_activity_collection()
    info = await collection.index_information()
    ttl_config = info.get("activity_created_at_ttl")
    assert ttl_config is not None
    assert ttl_config.get("expireAfterSeconds") == 864
    await close_activity_store()


async def test_activity_events_for_login_and_task_changes(
    activity_store: None,
    session: AsyncSession,
    user: User,
) -> None:
    settings = get_settings()
    settings.cache_enabled = False

    auth_form = OAuth2PasswordRequestForm(username=user.email, password="secret", scope="")
    service = ActivityLogService()

    response = await login(
        session=session,
        settings=settings,
        activity_service=service,
        form_data=auth_form,
    )
    assert response.user.email == user.email

    await asyncio.sleep(0.01)
    events_after_login = await service.list_recent(limit=5)
    assert len(events_after_login) == 1
    assert events_after_login[0].action is ActivityAction.LOGIN
    assert events_after_login[0].metadata.get("source") == "api"

    task_payload = TaskCreate(title="Write tests", description="Ensure activity log works.")
    task_read = await create_task(
        payload=task_payload,
        session=session,
        current_user=user,
        activity_service=service,
    )
    assert task_read.title == "Write tests"

    await asyncio.sleep(0.01)
    assert task_read.id is not None
    update_payload = TaskUpdate(status=TaskStatus.COMPLETED)
    updated = await update_task(
        task_id=task_read.id,
        payload=update_payload,
        session=session,
        current_user=user,
        activity_service=service,
    )
    assert updated.status == TaskStatus.COMPLETED

    feed = await service.list_recent(limit=5)
    assert len(feed) == 3
    assert feed[0].action is ActivityAction.TASK_UPDATED
    assert feed[0].metadata.get("changes", {}).get("status") == TaskStatus.COMPLETED.value
    assert feed[1].action is ActivityAction.TASK_CREATED
    assert feed[1].metadata.get("task_title") == task_payload.title
    assert feed[-1].action is ActivityAction.LOGIN

    db_events = await ActivityEvent.find_all().to_list()
    assert len(db_events) == len(feed)
