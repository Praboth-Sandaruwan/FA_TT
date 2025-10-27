"""Repository for aggregated task report persistence."""

from __future__ import annotations

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from ..models import TaskReport
from .base import BaseRepository


class TaskReportRepository(BaseRepository[TaskReport]):
    """Persistence helpers for ``TaskReport`` entities."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, TaskReport)

    async def get_by_owner(self, owner_id: int) -> TaskReport | None:
        result = await self.session.execute(select(TaskReport).where(TaskReport.owner_id == owner_id))
        return result.scalar_one_or_none()


__all__ = ["TaskReportRepository"]
