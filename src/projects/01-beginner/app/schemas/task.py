"""Task-related Pydantic schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..models import TaskStatus

TASK_READ_EXAMPLE = {
    "id": 1,
    "title": "Draft product documentation",
    "description": "Outline sections for the public API guide.",
    "status": TaskStatus.PENDING.value,
    "owner_id": 42,
    "created_at": "2023-01-01T12:00:00Z",
    "updated_at": "2023-01-02T08:30:00Z",
}


class TaskCreate(BaseModel):
    """Payload for creating a new task."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "title": "Draft product documentation",
                "description": "Outline sections for the public API guide.",
                "status": TaskStatus.PENDING.value,
            }
        }
    )

    title: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None)
    status: TaskStatus = Field(default=TaskStatus.PENDING)


class TaskUpdate(BaseModel):
    """Payload for partially updating an existing task."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "title": "Update API documentation",
                "status": TaskStatus.IN_PROGRESS.value,
            }
        }
    )

    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None)
    status: TaskStatus | None = Field(default=None)

    @model_validator(mode="after")
    def _ensure_payload_not_empty(self) -> "TaskUpdate":
        if not self.model_dump(exclude_unset=True, exclude_none=True):
            raise ValueError("At least one field must be provided for update.")
        return self


class TaskRead(BaseModel):
    """Public representation of a task."""

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={"example": TASK_READ_EXAMPLE},
    )

    id: int
    title: str
    description: str | None = None
    status: TaskStatus
    owner_id: int
    created_at: datetime
    updated_at: datetime


class TaskListResponse(BaseModel):
    """Paginated collection of tasks."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "items": [TASK_READ_EXAMPLE],
                "total": 1,
                "limit": 20,
                "offset": 0,
            }
        }
    )

    items: list[TaskRead]
    total: int
    limit: int
    offset: int


__all__ = [
    "TaskCreate",
    "TaskListResponse",
    "TaskRead",
    "TaskUpdate",
]
