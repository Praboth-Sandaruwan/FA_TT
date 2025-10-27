"""Routes exposing background job orchestration."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, status

from ...core.jobs import JobQueueUnavailableError, enqueue_task_report
from ...deps import CurrentUserDependency, DatabaseSessionDependency
from ...models import User, UserRole
from ...repositories import UserRepository
from ...schemas.report import JobEnqueueResponse, TaskReportJobRequest, TaskReportRead
from ...services.reports import TaskReportService

router = APIRouter(prefix="/jobs", tags=["jobs"])


def _require_user_id(user: User) -> int:
    if user.id is None:  # pragma: no cover - defensive guard
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authenticated user is missing an identifier.",
        )
    return user.id


def _is_admin(user: User) -> bool:
    return user.role == UserRole.ADMIN


def _ensure_owner_access(requested_owner_id: int, current_user: User) -> None:
    if _is_admin(current_user):
        return
    if requested_owner_id != _require_user_id(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not permitted to access reports for other owners.",
        )


def _as_timezone_aware(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


@router.post(
    "/task-report",
    response_model=JobEnqueueResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Enqueue a task report generation job",
)
async def enqueue_task_report_job(
    payload: TaskReportJobRequest,
    session: DatabaseSessionDependency,
    current_user: CurrentUserDependency,
) -> JobEnqueueResponse:
    requested_owner_id = payload.owner_id or _require_user_id(current_user)
    _ensure_owner_access(requested_owner_id, current_user)

    repository = UserRepository(session)
    owner = await repository.get(requested_owner_id)
    if owner is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Owner not found.")

    try:
        job = enqueue_task_report(owner_id=requested_owner_id, request_id=payload.request_id)
    except JobQueueUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Background job queue is unavailable.",
        ) from exc

    enqueued_at = _as_timezone_aware(job.enqueued_at)
    queue_name = job.origin or "default"
    return JobEnqueueResponse(
        job_id=job.id,
        queue=queue_name,
        owner_id=requested_owner_id,
        enqueued_at=enqueued_at,
    )


@router.get(
    "/task-report/{owner_id}",
    response_model=TaskReportRead,
    summary="Retrieve the latest generated task report",
)
async def get_task_report(
    owner_id: int,
    session: DatabaseSessionDependency,
    current_user: CurrentUserDependency,
) -> TaskReportRead:
    _ensure_owner_access(owner_id, current_user)
    service = TaskReportService(session)
    report = await service.get_report(owner_id)
    if report is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not available.")
    return TaskReportRead.model_validate(report)


__all__ = ["router"]
