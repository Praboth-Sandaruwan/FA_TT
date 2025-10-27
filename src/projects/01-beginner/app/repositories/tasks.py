"""Repository for interacting with task persistence models."""

from __future__ import annotations

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from ..models import Task, TaskStatus
from .base import BaseRepository


class TaskRepository(BaseRepository[Task]):
    """Concrete repository encapsulating ``Task`` persistence operations."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Task)

    async def list_for_owner(self, owner_id: int) -> list[Task]:
        """Return all tasks assigned to the given owner."""
        result = await self.session.execute(select(Task).where(Task.owner_id == owner_id))
        return list(result.scalars().all())

    async def get_for_owner(self, task_id: int, owner_id: int) -> Task | None:
        """Retrieve a task by ID ensuring it belongs to the provided owner."""
        result = await self.session.execute(
            select(Task).where(Task.id == task_id, Task.owner_id == owner_id)
        )
        return result.scalar_one_or_none()

    async def list_by_status(self, status: TaskStatus) -> list[Task]:
        """Return tasks filtered by status."""
        result = await self.session.execute(select(Task).where(Task.status == status))
        return list(result.scalars().all())
