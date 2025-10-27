"""Routes handling task CRUD operations."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query, Response, status

from ...core.cache import (
    TASK_LIST_CACHE_NAMESPACE,
    TASK_STATISTICS_CACHE_NAMESPACE,
    cache_get_or_set,
)
from ...deps import ActivityServiceDependency, CurrentUserDependency, DatabaseSessionDependency
from ...models import TaskStatus, User, UserRole
from ...schemas import TaskCreate, TaskListResponse, TaskRead, TaskStatistics, TaskUpdate
from ...services import TaskService

router = APIRouter(prefix="/tasks", tags=["tasks"])

LimitQuery = Annotated[
    int,
    Query(
        default=20,
        ge=1,
        le=100,
        description="Maximum number of tasks to return in a single response.",
    ),
]
OffsetQuery = Annotated[
    int,
    Query(
        default=0,
        ge=0,
        description="Number of tasks to skip before collecting results.",
    ),
]
StatusQuery = Annotated[
    TaskStatus | None,
    Query(
        default=None,
        description="Filter results to tasks matching the supplied status.",
    ),
]
OwnerQuery = Annotated[
    int | None,
    Query(
        default=None,
        ge=1,
        description="Restrict results to tasks owned by the provided user id.",
    ),
]


def _require_user_id(user: User) -> int:
    if user.id is None:  # pragma: no cover - defensive guard for inconsistent data
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authenticated user is missing an identifier.",
        )
    return user.id


def _is_admin(user: User) -> bool:
    return user.role == UserRole.ADMIN


def _map_task(task) -> TaskRead:
    return TaskRead.model_validate(task)


def _serialise_updates(updates: dict[str, Any]) -> dict[str, Any]:
    cleaned: dict[str, Any] = {}
    for key, value in updates.items():
        if isinstance(value, TaskStatus):
            cleaned[key] = value.value
        else:
            cleaned[key] = value
    return cleaned


@router.get(
    "/",
    response_model=TaskListResponse,
    summary="List tasks with pagination and optional filtering",
)
async def list_tasks(
    session: DatabaseSessionDependency,
    current_user: CurrentUserDependency,
    limit: LimitQuery = 20,
    offset: OffsetQuery = 0,
    status: StatusQuery = None,
    owner_id: OwnerQuery = None,
) -> TaskListResponse:
    service = TaskService(session)
    current_user_id = _require_user_id(current_user)
    effective_owner_id = owner_id

    if not _is_admin(current_user):
        if owner_id is not None and owner_id != current_user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not permitted to view tasks for other owners.",
            )
        effective_owner_id = current_user_id

    async def _build_response() -> TaskListResponse:
        tasks, total = await service.list_tasks_paginated(
            owner_id=effective_owner_id,
            status=status,
            limit=limit,
            offset=offset,
        )
        return TaskListResponse(
            items=[_map_task(task) for task in tasks],
            total=total,
            limit=limit,
            offset=offset,
        )

    owner_fragment = effective_owner_id if effective_owner_id is not None else "all"
    status_fragment = status.value if status is not None else "all"
    cache_key = f"owner={owner_fragment}:status={status_fragment}:limit={limit}:offset={offset}"
    return await cache_get_or_set(
        namespace=TASK_LIST_CACHE_NAMESPACE,
        key=cache_key,
        builder=_build_response,
        model=TaskListResponse,
    )


@router.get(
    "/statistics",
    response_model=TaskStatistics,
    summary="Aggregate task statistics",
)
async def get_task_statistics(
    session: DatabaseSessionDependency,
    current_user: CurrentUserDependency,
    owner_id: OwnerQuery = None,
) -> TaskStatistics:
    service = TaskService(session)
    current_user_id = _require_user_id(current_user)
    effective_owner_id = owner_id

    if not _is_admin(current_user):
        if owner_id is not None and owner_id != current_user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not permitted to view statistics for other owners.",
            )
        effective_owner_id = current_user_id

    owner_fragment = effective_owner_id if effective_owner_id is not None else "all"

    async def _build_statistics() -> TaskStatistics:
        stats = await service.get_task_statistics(effective_owner_id)
        return TaskStatistics(
            owner_id=stats.owner_id,
            total=stats.total,
            by_status=stats.by_status,
        )

    return await cache_get_or_set(
        namespace=TASK_STATISTICS_CACHE_NAMESPACE,
        key=f"owner={owner_fragment}",
        builder=_build_statistics,
        model=TaskStatistics,
    )


@router.get(
    "/{task_id}",
    response_model=TaskRead,
    summary="Retrieve a task by id",
)
async def get_task(
    task_id: int,
    session: DatabaseSessionDependency,
    current_user: CurrentUserDependency,
) -> TaskRead:
    service = TaskService(session)
    task = await service.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found.")

    current_user_id = _require_user_id(current_user)
    if not _is_admin(current_user) and task.owner_id != current_user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not permitted to view this task.",
        )

    return _map_task(task)


@router.post(
    "/",
    response_model=TaskRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new task",
)
async def create_task(
    payload: TaskCreate,
    session: DatabaseSessionDependency,
    current_user: CurrentUserDependency,
    activity_service: ActivityServiceDependency,
) -> TaskRead:
    service = TaskService(session)
    current_user_id = _require_user_id(current_user)

    try:
        task = await service.create_task(
            owner_id=current_user_id,
            title=payload.title,
            description=payload.description,
            status=payload.status,
        )
    except ValueError as exc:  # pragma: no cover - defensive guard
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    await activity_service.record_task_created(actor=current_user, task=task, source="api")
    return _map_task(task)


@router.patch(
    "/{task_id}",
    response_model=TaskRead,
    summary="Update an existing task",
)
async def update_task(
    task_id: int,
    payload: TaskUpdate,
    session: DatabaseSessionDependency,
    current_user: CurrentUserDependency,
    activity_service: ActivityServiceDependency,
) -> TaskRead:
    service = TaskService(session)
    updates = payload.model_dump(exclude_unset=True)
    changes = _serialise_updates(updates)

    try:
        if _is_admin(current_user):
            task = await service.update_task(task_id, **updates)
        else:
            current_user_id = _require_user_id(current_user)
            task = await service.update_task_for_owner(task_id, current_user_id, **updates)
    except PermissionError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not permitted to modify this task.",
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))

    await activity_service.record_task_updated(
        actor=current_user,
        task=task,
        source="api",
        changes=changes,
    )
    return _map_task(task)


@router.delete(
    "/{task_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a task",
)
async def delete_task(
    task_id: int,
    session: DatabaseSessionDependency,
    current_user: CurrentUserDependency,
) -> Response:
    service = TaskService(session)

    try:
        if _is_admin(current_user):
            deleted = await service.delete_task(task_id)
        else:
            current_user_id = _require_user_id(current_user)
            deleted = await service.delete_task_for_owner(task_id, current_user_id)
    except PermissionError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not permitted to delete this task.",
        )

    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found.")

    return Response(status_code=status.HTTP_204_NO_CONTENT)
