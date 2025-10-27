"""Database repositories for encapsulating persistence logic."""

from __future__ import annotations

from .reports import TaskReportRepository
from .tasks import TaskRepository
from .users import UserRepository

__all__ = ["TaskReportRepository", "TaskRepository", "UserRepository"]
