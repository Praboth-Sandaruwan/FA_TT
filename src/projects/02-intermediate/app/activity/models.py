from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Mapping

from beanie import Document
from pydantic import ConfigDict, Field, computed_field, field_validator


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ActivityAction(str, Enum):
    """Enumeration of activity event types recorded by the application."""

    LOGIN = "login"
    TASK_CREATED = "task_created"
    TASK_UPDATED = "task_updated"


class ActivityEvent(Document):
    """Beanie document capturing noteworthy user-facing events."""

    model_config = ConfigDict(str_strip_whitespace=True)

    action: ActivityAction = Field(description="Identifier describing the event type.")
    summary: str = Field(max_length=240, description="Human readable summary of the event.")
    user_id: int | None = Field(default=None, description="Identifier of the actor, if available.")
    user_email: str | None = Field(default=None, description="Email address of the actor.")
    user_display_name: str | None = Field(default=None, description="Display name of the actor.")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Structured metadata attached to the event.")
    source: str | None = Field(default=None, max_length=40, description="Origin of the event (api, web, etc).")
    created_at: datetime = Field(default_factory=_utcnow, description="Timestamp indicating when the event occurred.")

    @field_validator("summary", mode="before")
    @classmethod
    def _clean_summary(cls, value: object) -> str:
        text = str(value or "").strip()
        if not text:
            raise ValueError("summary must not be empty")
        return text[:240]

    @field_validator("user_email", mode="before")
    @classmethod
    def _normalise_email(cls, value: object) -> str | None:
        if value is None:
            return None
        email = str(value).strip().lower()
        return email or None

    @field_validator("user_display_name", mode="before")
    @classmethod
    def _clean_display_name(cls, value: object) -> str | None:
        if value is None:
            return None
        name = str(value).strip()
        return name or None

    @field_validator("source", mode="before")
    @classmethod
    def _clean_source(cls, value: object) -> str | None:
        if value is None:
            return None
        source = str(value).strip().lower()
        return source or None

    @field_validator("metadata", mode="before")
    @classmethod
    def _ensure_metadata(cls, value: object) -> dict[str, Any]:
        if value is None:
            return {}
        if isinstance(value, Mapping):
            return {str(key): val for key, val in value.items()}
        return {}

    @computed_field(return_type=str)
    def action_label(self) -> str:
        lookup = {
            ActivityAction.LOGIN: "Login",
            ActivityAction.TASK_CREATED: "Task created",
            ActivityAction.TASK_UPDATED: "Task updated",
        }
        return lookup.get(self.action, self.action.value.replace("_", " ").title())

    class Settings:
        name = "activity_events"


__all__ = ["ActivityAction", "ActivityEvent"]
