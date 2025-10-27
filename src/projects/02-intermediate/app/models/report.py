"""Reporting models for summarising task data."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlmodel import Field, Relationship, SQLModel

from .common import TimestampMixin, utcnow

if TYPE_CHECKING:  # pragma: no cover - typing only
    from .user import User


class TaskReport(TimestampMixin, table=True):
    """Aggregated snapshot of a user's tasks."""

    __tablename__ = "task_reports"
    __table_args__ = (
        sa.UniqueConstraint("owner_id", name="uq_task_reports_owner_id"),
    )

    id: int | None = Field(default=None, primary_key=True)
    owner_id: int = Field(
        sa_column=sa.Column(
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
    )
    total_tasks: int = Field(sa_column=sa.Column(sa.Integer(), nullable=False, server_default="0"))
    pending_tasks: int = Field(sa_column=sa.Column(sa.Integer(), nullable=False, server_default="0"))
    in_progress_tasks: int = Field(sa_column=sa.Column(sa.Integer(), nullable=False, server_default="0"))
    completed_tasks: int = Field(sa_column=sa.Column(sa.Integer(), nullable=False, server_default="0"))
    cancelled_tasks: int = Field(sa_column=sa.Column(sa.Integer(), nullable=False, server_default="0"))
    generated_at: datetime = Field(
        default_factory=utcnow,
        sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    owner: "User" = Relationship(back_populates="task_report")


__all__ = ["TaskReport"]
