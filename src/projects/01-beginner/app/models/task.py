"""Task domain models built with SQLModel."""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlmodel import Field, Relationship, SQLModel

from .common import TimestampMixin

if TYPE_CHECKING:  # pragma: no cover - imported for typing only
    from .user import User


class TaskStatus(str, Enum):
    """Enumeration of possible task states."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class TaskBase(SQLModel, table=False):
    """Shared attributes for task models."""

    title: str = Field(
        max_length=255,
        sa_column=sa.Column(sa.String(length=255), nullable=False),
    )
    description: str | None = Field(
        default=None,
        sa_column=sa.Column(sa.Text(), nullable=True),
    )
    status: TaskStatus = Field(
        default=TaskStatus.PENDING,
        sa_column=sa.Column(
            sa.Enum(TaskStatus, name="task_status", native_enum=False, validate_strings=True),
            nullable=False,
            server_default=TaskStatus.PENDING.value,
        ),
    )
    owner_id: int = Field(
        sa_column=sa.Column(
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
    )


class Task(TaskBase, TimestampMixin, table=True):
    """Persistent task model."""

    __tablename__ = "tasks"
    __table_args__ = (
        sa.CheckConstraint("length(title) > 0", name="ck_tasks_title_length"),
        sa.Index("ix_tasks_owner_id", "owner_id"),
    )

    id: int | None = Field(default=None, primary_key=True)
    owner: "User" = Relationship(back_populates="tasks")


__all__ = ["Task", "TaskBase", "TaskStatus"]
