"""Session management helpers."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from .base import SessionProtocol

__all__ = ["session_scope"]


@contextmanager
def session_scope(session: SessionProtocol) -> Iterator[SessionProtocol]:
    """Provide a transactional scope around a series of operations."""
    try:
        yield session
        session.commit()
    except Exception:  # pragma: no cover - defensive programming
        session.rollback()
        raise
    finally:
        session.close()
