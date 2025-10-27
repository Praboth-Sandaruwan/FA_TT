"""Services supporting reporting workflows."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy.exc import IntegrityError
from sqlmodel.ext.asyncio.session import AsyncSession

from ..models import TaskReport, TaskStatus
from ..models.common import utcnow
from ..repositories import TaskReportRepository, TaskRepository

logger = logging.getLogger("projects.02-intermediate.app.services.reports")


@dataclass(slots=True)
class TaskReportSummary:
    """Value object describing task counts for an owner."""

    owner_id: int
    total_tasks: int
    pending_tasks: int
    in_progress_tasks: int
    completed_tasks: int
    cancelled_tasks: int


class TaskReportService:
    """Business logic for generating task summary reports."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._task_repository = TaskRepository(session)
        self._report_repository = TaskReportRepository(session)

    async def get_report(self, owner_id: int) -> TaskReport | None:
        """Retrieve the latest report for a given owner."""

        return await self._report_repository.get_by_owner(owner_id)

    async def generate_report(self, owner_id: int) -> TaskReport:
        """Generate or refresh the aggregated task report for the owner."""

        counts = await self._task_repository.count_by_status(owner_id=owner_id)
        summary = self._build_summary(owner_id, counts)
        existing = await self._report_repository.get_by_owner(owner_id)

        if existing is None:
            report = TaskReport(
                owner_id=owner_id,
                total_tasks=summary.total_tasks,
                pending_tasks=summary.pending_tasks,
                in_progress_tasks=summary.in_progress_tasks,
                completed_tasks=summary.completed_tasks,
                cancelled_tasks=summary.cancelled_tasks,
                generated_at=utcnow(),
            )
            await self._report_repository.add(report)
        else:
            self._apply_summary(existing, summary)
            report = existing

        try:
            await self._session.commit()
        except IntegrityError:
            logger.info("Detected concurrent report creation for owner %s; retrying as update.", owner_id)
            await self._session.rollback()
            report = await self._retry_update(owner_id, summary)
        await self._report_repository.refresh(report)
        return report

    def _apply_summary(self, report: TaskReport, summary: TaskReportSummary) -> None:
        report.total_tasks = summary.total_tasks
        report.pending_tasks = summary.pending_tasks
        report.in_progress_tasks = summary.in_progress_tasks
        report.completed_tasks = summary.completed_tasks
        report.cancelled_tasks = summary.cancelled_tasks
        report.generated_at = utcnow()

    async def _retry_update(self, owner_id: int, summary: TaskReportSummary) -> TaskReport:
        existing = await self._report_repository.get_by_owner(owner_id)
        if existing is None:
            logger.error("Failed to locate task report during retry for owner %s", owner_id)
            raise
        self._apply_summary(existing, summary)
        await self._session.commit()
        return existing

    def _build_summary(self, owner_id: int, counts: dict[TaskStatus, int]) -> TaskReportSummary:
        pending = counts.get(TaskStatus.PENDING, 0)
        in_progress = counts.get(TaskStatus.IN_PROGRESS, 0)
        completed = counts.get(TaskStatus.COMPLETED, 0)
        cancelled = counts.get(TaskStatus.CANCELLED, 0)
        total = pending + in_progress + completed + cancelled
        return TaskReportSummary(
            owner_id=owner_id,
            total_tasks=total,
            pending_tasks=pending,
            in_progress_tasks=in_progress,
            completed_tasks=completed,
            cancelled_tasks=cancelled,
        )


__all__ = ["TaskReportService", "TaskReportSummary"]
