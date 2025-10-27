"""User domain models built with SQLModel."""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlmodel import Field, Relationship, SQLModel

from .common import TimestampMixin

if TYPE_CHECKING:  # pragma: no cover - imported for typing only
    from .task import Task


class UserBase(SQLModel, table=False):
    """Shared attributes for user models."""

    email: str = Field(
        max_length=320,
        sa_column=sa.Column(
            sa.String(length=320),
            nullable=False,
            unique=True,
        ),
    )
    full_name: str | None = Field(
        default=None,
        max_length=255,
        sa_column=sa.Column(sa.String(length=255), nullable=True),
    )
    is_active: bool = Field(
        default=True,
        sa_column=sa.Column(
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )


class User(UserBase, TimestampMixin, table=True):
    """Persistent user model."""

    __tablename__ = "users"
    __table_args__ = (sa.Index("ix_users_email", "email"),)

    id: int | None = Field(default=None, primary_key=True)
    tasks: list["Task"] = Relationship(
        back_populates="owner",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )


__all__ = ["User", "UserBase"]
