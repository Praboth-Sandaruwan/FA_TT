"""Database repositories for encapsulating persistence logic."""

from __future__ import annotations

from .tasks import TaskRepository
from .users import UserRepository

__all__ = ["TaskRepository", "UserRepository"]
