"""Job implementations related to reporting and analytics."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from sqlmodel.ext.asyncio.session import AsyncSession

from ..core.context import bind_request_id, clear_request_id, reset_request_id
from ..core.jobs import execute_in_job_session
from ..services.reports import TaskReportService
from ..schemas.report import TaskReportRead

logger = logging.getLogger("projects.02-intermediate.app.jobs.reporting")


async def _generate_task_report(owner_id: int) -> TaskReportRead:
    async def _invoke(session: AsyncSession) -> TaskReportRead:
        service = TaskReportService(session)
        report = await service.generate_report(owner_id)
        return TaskReportRead.model_validate(report)

    return await execute_in_job_session(_invoke)


def generate_task_report_job(owner_id: int, request_id: str | None = None) -> dict[str, Any]:
    """Generate and persist a summary report for a user's tasks."""

    if owner_id <= 0:
        raise ValueError("owner_id must be a positive integer")

    token = None
    if request_id:
        token = bind_request_id(request_id)
    else:
        clear_request_id()

    try:
        result = asyncio.run(_generate_task_report(owner_id))
        payload = result.model_dump()
        logger.info(
            "Generated task report for owner %s",
            owner_id,
            extra={"owner_id": owner_id},
        )
        return payload
    finally:
        if token is not None:
            reset_request_id(token)
        else:
            clear_request_id()


__all__ = ["generate_task_report_job"]
