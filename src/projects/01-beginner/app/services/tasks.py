"""Service layer encapsulating task-related operations."""

from __future__ import annotations

from sqlmodel.ext.asyncio.session import AsyncSession

from ..models import Task, TaskStatus
from ..repositories import TaskRepository, UserRepository


class TaskService:
    """High-level business orchestration for ``Task`` entities."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repository = TaskRepository(session)
        self._user_repository = UserRepository(session)

    @property
    def repository(self) -> TaskRepository:
        """Expose the underlying repository for advanced scenarios."""
        return self._repository

    async def create_task(
        self,
        *,
        owner_id: int,
        title: str,
        description: str | None = None,
        status: TaskStatus = TaskStatus.PENDING,
    ) -> Task:
        """Create a new task belonging to the specified owner."""
        owner = await self._user_repository.get(owner_id)
        if owner is None:
            raise ValueError(f"Owner {owner_id} does not exist")
        task = Task(
            owner_id=owner_id,
            title=title,
            description=description,
            status=status,
        )
        await self._repository.add(task)
        await self._session.commit()
        await self._repository.refresh(task)
        return task

    async def get_task(self, task_id: int) -> Task | None:
        """Retrieve a task by primary key."""
        return await self._repository.get(task_id)

    async def get_task_for_owner(self, task_id: int, owner_id: int) -> Task | None:
        """Retrieve a task ensuring it belongs to the provided owner."""
        return await self._repository.get_for_owner(task_id, owner_id)

    async def list_tasks(self) -> list[Task]:
        """Return all tasks in the system."""
        return await self._repository.list()

    async def list_tasks_for_owner(self, owner_id: int) -> list[Task]:
        """Return all tasks assigned to a specific owner."""
        return await self._repository.list_for_owner(owner_id)

    async def list_tasks_by_status(self, status: TaskStatus) -> list[Task]:
        """Return tasks filtered by their status."""
        return await self._repository.list_by_status(status)

    async def update_task(
        self,
        task_id: int,
        *,
        title: str | None = None,
        description: str | None = None,
        status: TaskStatus | None = None,
    ) -> Task:
        """Apply updates to a task and persist the changes."""
        task = await self._repository.get(task_id)
        if task is None:
            raise ValueError(f"Task {task_id} does not exist")
        if title is not None:
            task.title = title
        if description is not None:
            task.description = description
        if status is not None:
            task.status = status
        await self._session.commit()
        await self._repository.refresh(task)
        return task

    async def reassign_task(self, task_id: int, owner_id: int) -> Task:
        """Transfer a task to a different owner."""
        task = await self._repository.get(task_id)
        if task is None:
            raise ValueError(f"Task {task_id} does not exist")
        owner = await self._user_repository.get(owner_id)
        if owner is None:
            raise ValueError(f"Owner {owner_id} does not exist")
        task.owner_id = owner_id
        await self._session.commit()
        await self._repository.refresh(task)
        return task

    async def delete_task(self, task_id: int) -> bool:
        """Delete a task by ID, returning ``True`` iff a record was removed."""
        task = await self._repository.get(task_id)
        if task is None:
            return False
        await self._repository.delete(task)
        await self._session.commit()
        return True
