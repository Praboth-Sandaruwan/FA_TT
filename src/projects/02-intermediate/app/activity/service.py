from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from enum import Enum
from typing import Any, TYPE_CHECKING

from .models import ActivityAction, ActivityEvent

if TYPE_CHECKING:  # pragma: no cover - imported for typing only
    from ..models.task import Task
    from ..models.user import User


def _safe_int(value: Any) -> int | None:
    try:
        return int(value)  # type: ignore[return-value]
    except (TypeError, ValueError):  # pragma: no cover - defensive guard
        return None


def _ensure_tzaware(timestamp: datetime) -> datetime:
    if timestamp.tzinfo is None:
        return timestamp.replace(tzinfo=timezone.utc)
    return timestamp


def _serialise_value(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return _ensure_tzaware(value).isoformat()
    if isinstance(value, Mapping):
        return {str(key): _serialise_value(val) for key, val in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_serialise_value(item) for item in value]
    return value


def _normalise_metadata(metadata: Mapping[str, Any] | None) -> dict[str, Any]:
    if not metadata:
        return {}
    return {str(key): _serialise_value(value) for key, value in metadata.items()}


def _display_name(user: "User" | None) -> str | None:
    if user is None:
        return None
    name = (user.full_name or "").strip()
    if name:
        return name
    email = getattr(user, "email", None)
    if isinstance(email, str) and email.strip():
        return email.strip()
    return None


class ActivityLogService:
    """High level helper encapsulating activity log operations."""

    def __init__(self, *, default_page_size: int = 25) -> None:
        self._default_page_size = max(default_page_size, 1)

    async def record_event(
        self,
        *,
        action: ActivityAction,
        summary: str,
        actor: "User" | None = None,
        metadata: Mapping[str, Any] | None = None,
        source: str | None = None,
    ) -> ActivityEvent:
        event = ActivityEvent(
            action=action,
            summary=summary,
            user_id=_safe_int(getattr(actor, "id", None)),
            user_email=getattr(actor, "email", None),
            user_display_name=_display_name(actor),
            metadata=_normalise_metadata(metadata),
            source=source,
        )
        await event.insert()
        return event

    async def record_login(self, actor: "User", *, source: str) -> ActivityEvent:
        summary = f"Signed in via {source.upper()}"
        metadata = {"source": source}
        return await self.record_event(
            action=ActivityAction.LOGIN,
            summary=summary,
            actor=actor,
            metadata=metadata,
            source=source,
        )

    async def record_task_created(
        self,
        *,
        actor: "User",
        task: "Task",
        source: str,
    ) -> ActivityEvent:
        title = (getattr(task, "title", "") or "").strip()
        summary = f'Created task "{title}"'
        metadata = {
            "task_id": _safe_int(getattr(task, "id", None)),
            "task_title": getattr(task, "title", None),
            "status": getattr(task, "status", None),
            "source": source,
        }
        return await self.record_event(
            action=ActivityAction.TASK_CREATED,
            summary=summary,
            actor=actor,
            metadata=metadata,
            source=source,
        )

    async def record_task_updated(
        self,
        *,
        actor: "User",
        task: "Task",
        source: str,
        changes: Mapping[str, Any] | None = None,
    ) -> ActivityEvent:
        fields: Sequence[str] = tuple(sorted(changes.keys())) if changes else ()
        title = (getattr(task, "title", "") or "").strip()
        if fields:
            descriptor = ", ".join(fields)
            summary = f'Updated task "{title}" ({descriptor})'
        else:
            summary = f'Updated task "{title}"'
        metadata = {
            "task_id": _safe_int(getattr(task, "id", None)),
            "task_title": getattr(task, "title", None),
            "status": getattr(task, "status", None),
            "changes": _normalise_metadata(changes),
            "source": source,
        }
        return await self.record_event(
            action=ActivityAction.TASK_UPDATED,
            summary=summary,
            actor=actor,
            metadata=metadata,
            source=source,
        )

    async def list_recent(self, *, limit: int | None = None) -> list[ActivityEvent]:
        page_size = self._default_page_size if limit is None else max(int(limit), 1)
        return (
            await ActivityEvent.find_all()
            .sort("-created_at")
            .limit(page_size)
            .to_list()
        )
