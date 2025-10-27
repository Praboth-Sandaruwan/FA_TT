"""Database abstractions used across the application."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

__all__ = ["SessionProtocol"]


@runtime_checkable
class SessionProtocol(Protocol):
    """Protocol describing the minimal database session surface we rely on."""

    def close(self) -> None:  # pragma: no cover - interface definition
        """Close the underlying session resources."""

    def commit(self) -> None:  # pragma: no cover - interface definition
        """Commit any pending database changes."""

    def rollback(self) -> None:  # pragma: no cover - interface definition
        """Rollback the current database transaction."""
