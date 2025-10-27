"""Schemas for reporting and background job APIs."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field
from pydantic.config import ConfigDict


class TaskReportRead(BaseModel):
    """API representation of a generated task report."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    owner_id: int
    total_tasks: int = Field(ge=0)
    pending_tasks: int = Field(ge=0)
    in_progress_tasks: int = Field(ge=0)
    completed_tasks: int = Field(ge=0)
    cancelled_tasks: int = Field(ge=0)
    generated_at: datetime
    updated_at: datetime
    created_at: datetime


class TaskReportJobRequest(BaseModel):
    """Payload for enqueuing a task report generation job."""

    owner_id: int | None = Field(
        default=None,
        ge=1,
        description="Generate the report for a specific owner. Defaults to the current user.",
    )
    request_id: str | None = Field(
        default=None,
        description="Optional idempotency key to reuse an existing queued job.",
        min_length=1,
        max_length=128,
    )


class JobEnqueueResponse(BaseModel):
    """Metadata about an enqueued background job."""

    job_id: str
    queue: str
    owner_id: int
    enqueued_at: datetime
    status: str = "queued"


__all__ = ["JobEnqueueResponse", "TaskReportJobRequest", "TaskReportRead"]
