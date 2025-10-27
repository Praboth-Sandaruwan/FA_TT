"""SQLModel metadata registration for Alembic autogeneration."""

from __future__ import annotations

from sqlmodel import SQLModel

# Import models so that SQLModel.metadata is populated for Alembic.
from ..models import Task, User  # noqa: F401

__all__ = ["SQLModel", "Task", "User"]
