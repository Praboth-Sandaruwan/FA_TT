"""Routes handling task CRUD operations."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Response, status

from ...deps import CurrentUserDependency, DatabaseSessionDependency
from ...models import TaskStatus, User, UserRole
from ...schemas import TaskCreate, TaskListResponse, TaskRead, TaskUpdate
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
) -> TaskRead:
    service = TaskService(session)
    updates = payload.model_dump(exclude_unset=True)

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
