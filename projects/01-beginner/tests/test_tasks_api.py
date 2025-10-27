from __future__ import annotations

from typing import Callable
from importlib import import_module

import pytest
from httpx import AsyncClient

BEGINNER_PACKAGE = "projects.01-beginner"


def load_beginner_module(path: str):
    return import_module(f"{BEGINNER_PACKAGE}.{path}")

models_module = load_beginner_module("app.models")

TaskStatus = getattr(models_module, "TaskStatus")
UserRole = getattr(models_module, "UserRole")

pytestmark = pytest.mark.asyncio


async def test_task_crud_flow_with_pagination_and_filters(
    client: AsyncClient,
    authenticated_user: Callable[..., "AuthenticatedUser"],
) -> None:
    owner = await authenticated_user(full_name="Task User")
    headers = owner.headers

    first_task_payload = {
        "title": "Write onboarding checklist",
        "description": "Prepare the initial onboarding tasks for new teammates.",
    }
    first_task_response = await client.post("/api/tasks", json=first_task_payload, headers=headers)
    assert first_task_response.status_code == 201
    first_task = first_task_response.json()
    assert first_task["owner_id"] == owner.id
    assert first_task["status"] == TaskStatus.PENDING.value

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
    assert [task["id"] for task in list_payload["items"]] == [first_task["id"], second_task["id"]]

    first_page = await client.get("/api/tasks", params={"limit": 1}, headers=headers)
    assert first_page.status_code == 200
    assert first_page.json()["items"][0]["id"] == first_task["id"]

    second_page = await client.get(
        "/api/tasks",
        params={"limit": 1, "offset": 1},
        headers=headers,
    )
    assert second_page.status_code == 200
    assert second_page.json()["items"][0]["id"] == second_task["id"]

    filtered = await client.get(
        "/api/tasks",
        params={"status": TaskStatus.IN_PROGRESS.value},
        headers=headers,
    )
    assert filtered.status_code == 200
    assert filtered.json()["items"][0]["id"] == second_task["id"]

    detail_response = await client.get(f"/api/tasks/{first_task['id']}", headers=headers)
    assert detail_response.status_code == 200
    assert detail_response.json()["title"] == first_task_payload["title"]

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


async def test_task_authorization_enforced_for_non_owner(
    client: AsyncClient,
    authenticated_user: Callable[..., "AuthenticatedUser"],
) -> None:
    owner = await authenticated_user(full_name="Owner User")
    owner_headers = owner.headers

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

    other_user = await authenticated_user(full_name="Other User")
    other_headers = other_user.headers

    other_list = await client.get("/api/tasks", headers=other_headers)
    assert other_list.status_code == 200
    assert other_list.json()["total"] == 0

    forbidden_list = await client.get(
        "/api/tasks",
        params={"owner_id": owner.id},
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


async def test_admin_can_manage_other_users_tasks(
    client: AsyncClient,
    authenticated_user: Callable[..., "AuthenticatedUser"],
) -> None:
    managed_user = await authenticated_user(full_name="Managed User")
    managed_headers = managed_user.headers

    task_response = await client.post(
        "/api/tasks",
        json={
            "title": "Task awaiting review",
            "description": "Needs administrative approval.",
        },
        headers=managed_headers,
    )
    assert task_response.status_code == 201
    task_id = task_response.json()["id"]

    admin = await authenticated_user(role=UserRole.ADMIN, full_name="Admin User")
    admin_headers = admin.headers

    admin_list = await client.get(
        "/api/tasks",
        params={"owner_id": managed_user.id},
        headers=admin_headers,
    )
    assert admin_list.status_code == 200
    assert admin_list.json()["total"] == 1
    assert admin_list.json()["items"][0]["id"] == task_id

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


async def test_update_missing_task_returns_not_found(
    client: AsyncClient,
    authenticated_user: Callable[..., "AuthenticatedUser"],
) -> None:
    user = await authenticated_user()

    response = await client.patch(
        "/api/tasks/9999",
        json={"status": TaskStatus.COMPLETED.value},
        headers=user.headers,
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Task 9999 does not exist"


async def test_delete_missing_task_returns_not_found(
    client: AsyncClient,
    authenticated_user: Callable[..., "AuthenticatedUser"],
) -> None:
    user = await authenticated_user()

    response = await client.delete("/api/tasks/9999", headers=user.headers)
    assert response.status_code == 404
    assert response.json()["detail"] == "Task not found."
