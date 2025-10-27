"""User-facing Pydantic schemas."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, EmailStr

from ..models import UserRole


class UserPublic(BaseModel):
    """Minimal public representation of a user."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    full_name: str | None = None
    role: UserRole


__all__ = ["UserPublic"]
