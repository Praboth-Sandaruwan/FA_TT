"""Shared model mixins and utilities."""

from __future__ import annotations

from datetime import datetime, timezone

import sqlalchemy as sa
from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


class TimestampMixin(SQLModel, table=False):
    """Mixin that provides created/updated timestamp columns."""

    created_at: datetime = Field(
        default_factory=utcnow,
        nullable=False,
        sa_type=sa.DateTime(timezone=True),
        sa_column_kwargs={"server_default": sa.func.now()},
    )
    updated_at: datetime = Field(
        default_factory=utcnow,
        nullable=False,
        sa_type=sa.DateTime(timezone=True),
        sa_column_kwargs={
            "server_default": sa.func.now(),
            "server_onupdate": sa.func.now(),
        },
    )


__all__ = ["TimestampMixin", "utcnow"]
