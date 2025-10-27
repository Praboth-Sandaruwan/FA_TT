from __future__ import annotations

from collections.abc import AsyncIterator
from importlib import import_module

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

BEGINNER_PACKAGE = "projects.01-beginner"


def load_beginner_module(path: str):
    return import_module(f"{BEGINNER_PACKAGE}.{path}")


config_module = load_beginner_module("app.core.config")
deps_module = load_beginner_module("app.deps")
main_module = load_beginner_module("app.main")
models_module = load_beginner_module("app.models")
services_module = load_beginner_module("app.services")

create_app = getattr(main_module, "create_app")
get_settings = getattr(config_module, "get_settings")
get_db_session = getattr(deps_module, "get_db_session")
TaskStatus = getattr(models_module, "TaskStatus")
UserRole = getattr(models_module, "UserRole")
UserService = getattr(services_module, "UserService")


@pytest_asyncio.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    engine: AsyncEngine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
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


@pytest_asyncio.fixture
async def app(session: AsyncSession) -> AsyncIterator[FastAPI]:
    get_settings.cache_clear()
    settings = get_settings()
    original_access = settings.access_token_expire_minutes
    original_refresh = settings.refresh_token_expire_minutes
    application = create_app()

    async def _override_db_session():
        yield session

    application.dependency_overrides[get_db_session] = _override_db_session
    settings.access_token_expire_minutes = 5
    settings.refresh_token_expire_minutes = 60

    try:
        yield application
    finally:
        application.dependency_overrides.clear()
        settings.access_token_expire_minutes = original_access
        settings.refresh_token_expire_minutes = original_refresh


@pytest_asyncio.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(app=app, base_url="http://testserver") as client:
        yield client


@pytest.mark.asyncio
async def test_task_crud_flow_with_pagination_and_filters(client: AsyncClient) -> None:
    signup_response = await client.post(
        "/api/auth/signup",
        json={
            "email": "tasks-user@example.com",
            "password": "StrongPass123!",
            "full_name": "Task User",
        },
    )
    assert signup_response.status_code == 201
    signup_json = signup_response.json()
    user_id = signup_json["user"]["id"]
    access_token = signup_json["tokens"]["access_token"]
    headers = {"Authorization": f"Bearer {access_token}"}

    first_task_payload = {
        "title": "Write onboarding checklist",
        "description": "Prepare the initial onboarding tasks for new teammates.",
    }
    first_task_response = await client.post("/api/tasks", json=first_task_payload, headers=headers)
    assert first_task_response.status_code == 201
    first_task = first_task_response.json()
    assert first_task["title"] == first_task_payload["title"]
    assert first_task["status"] == TaskStatus.PENDING.value
    assert first_task["owner_id"] == user_id

    second_task_payload = {
        "title": "Publish API documentation",
        "description": "Finalise the public API documentation site.",
        "status": TaskStatus.IN_PROGRESS.value,
    }
    second_task_response = await client.post("/api/tasks", json=second_task_payload, headers=headers)
    assert second_task_response.status_code == 201
    second_task = second_task_response.json()
    assert second_task["status"] == TaskStatus.IN_PROGRESS.value

    list_response = await client.get("/api/tasks", headers=headers)
    assert list_response.status_code == 200
    list_payload = list_response.json()
    assert list_payload["total"] == 2
    assert list_payload["limit"] == 20
    assert list_payload["offset"] == 0
    assert [task["id"] for task in list_payload["items"]] == [first_task["id"], second_task["id"]]

    first_page = await client.get("/api/tasks", params={"limit": 1}, headers=headers)
    assert first_page.status_code == 200
    first_page_json = first_page.json()
    assert first_page_json["limit"] == 1
    assert first_page_json["total"] == 2
    assert len(first_page_json["items"]) == 1
    assert first_page_json["items"][0]["id"] == first_task["id"]

    second_page = await client.get(
        "/api/tasks",
        params={"limit": 1, "offset": 1},
        headers=headers,
    )
    assert second_page.status_code == 200
    second_page_json = second_page.json()
    assert second_page_json["limit"] == 1
    assert second_page_json["offset"] == 1
    assert second_page_json["items"][0]["id"] == second_task["id"]

    filtered = await client.get(
        "/api/tasks",
        params={"status": TaskStatus.IN_PROGRESS.value},
        headers=headers,
    )
    assert filtered.status_code == 200
    filtered_json = filtered.json()
    assert filtered_json["total"] == 1
    assert filtered_json["items"][0]["id"] == second_task["id"]

    detail_response = await client.get(f"/api/tasks/{first_task['id']}", headers=headers)
    assert detail_response.status_code == 200
    detail_json = detail_response.json()
    assert detail_json["title"] == first_task_payload["title"]

    update_response = await client.patch(
        f"/api/tasks/{second_task['id']}",
        json={
            "status": TaskStatus.COMPLETED.value,
            "description": "Documentation site is live.",
        },
        headers=headers,
    )
    assert update_response.status_code == 200
    updated_task = update_response.json()
    assert updated_task["status"] == TaskStatus.COMPLETED.value
    assert updated_task["description"] == "Documentation site is live."

    delete_response = await client.delete(f"/api/tasks/{first_task['id']}", headers=headers)
    assert delete_response.status_code == 204

    remaining = await client.get("/api/tasks", headers=headers)
    assert remaining.status_code == 200
    remaining_json = remaining.json()
    assert remaining_json["total"] == 1
    assert remaining_json["items"][0]["id"] == second_task["id"]

    missing = await client.get(f"/api/tasks/{first_task['id']}", headers=headers)
    assert missing.status_code == 404


@pytest.mark.asyncio
async def test_task_authorization_enforced_for_non_owner(client: AsyncClient) -> None:
    owner_signup = await client.post(
        "/api/auth/signup",
        json={
            "email": "task-owner@example.com",
            "password": "OwnerPass123!",
            "full_name": "Owner User",
        },
    )
    assert owner_signup.status_code == 201
    owner_json = owner_signup.json()
    owner_id = owner_json["user"]["id"]
    owner_headers = {"Authorization": f"Bearer {owner_json['tokens']['access_token']}"}

    task_response = await client.post(
        "/api/tasks",
        json={
            "title": "Owner task",
            "description": "This task belongs to the owner user.",
        },
        headers=owner_headers,
    )
    assert task_response.status_code == 201
    task_id = task_response.json()["id"]

    other_signup = await client.post(
        "/api/auth/signup",
        json={
            "email": "other-user@example.com",
            "password": "OtherPass123!",
            "full_name": "Other User",
        },
    )
    assert other_signup.status_code == 201
    other_headers = {"Authorization": f"Bearer {other_signup.json()['tokens']['access_token']}"}

    other_list = await client.get("/api/tasks", headers=other_headers)
    assert other_list.status_code == 200
    assert other_list.json()["total"] == 0

    forbidden_list = await client.get(
        "/api/tasks",
        params={"owner_id": owner_id},
        headers=other_headers,
    )
    assert forbidden_list.status_code == 403

    forbidden_get = await client.get(f"/api/tasks/{task_id}", headers=other_headers)
    assert forbidden_get.status_code == 403

    forbidden_update = await client.patch(
        f"/api/tasks/{task_id}",
        json={"status": TaskStatus.CANCELLED.value},
        headers=other_headers,
    )
    assert forbidden_update.status_code == 403

    forbidden_delete = await client.delete(f"/api/tasks/{task_id}", headers=other_headers)
    assert forbidden_delete.status_code == 403

    still_exists = await client.get(f"/api/tasks/{task_id}", headers=owner_headers)
    assert still_exists.status_code == 200


@pytest.mark.asyncio
async def test_admin_can_manage_other_users_tasks(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    user_signup = await client.post(
        "/api/auth/signup",
        json={
            "email": "managed-user@example.com",
            "password": "ManagedPass123!",
            "full_name": "Managed User",
        },
    )
    assert user_signup.status_code == 201
    user_json = user_signup.json()
    user_id = user_json["user"]["id"]
    user_headers = {"Authorization": f"Bearer {user_json['tokens']['access_token']}"}

    task_response = await client.post(
        "/api/tasks",
        json={
            "title": "Task awaiting review",
            "description": "Needs administrative approval.",
        },
        headers=user_headers,
    )
    assert task_response.status_code == 201
    task_id = task_response.json()["id"]

    admin_email = "admin@example.com"
    admin_password = "AdminPass123!"
    user_service = UserService(session)
    admin_user = await user_service.create_user(
        email=admin_email,
        password=admin_password,
        full_name="Admin User",
        role=UserRole.ADMIN,
    )
    assert admin_user.id is not None

    admin_login = await client.post(
        "/api/auth/login",
        data={"username": admin_email, "password": admin_password},
    )
    assert admin_login.status_code == 200
    admin_token = admin_login.json()["tokens"]["access_token"]
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    admin_list = await client.get(
        "/api/tasks",
        params={"owner_id": user_id},
        headers=admin_headers,
    )
    assert admin_list.status_code == 200
    admin_list_json = admin_list.json()
    assert admin_list_json["total"] == 1
    assert admin_list_json["items"][0]["id"] == task_id

    admin_update = await client.patch(
        f"/api/tasks/{task_id}",
        json={"status": TaskStatus.CANCELLED.value},
        headers=admin_headers,
    )
    assert admin_update.status_code == 200
    assert admin_update.json()["status"] == TaskStatus.CANCELLED.value

    admin_delete = await client.delete(f"/api/tasks/{task_id}", headers=admin_headers)
    assert admin_delete.status_code == 204

    admin_missing = await client.get(f"/api/tasks/{task_id}", headers=admin_headers)
    assert admin_missing.status_code == 404
