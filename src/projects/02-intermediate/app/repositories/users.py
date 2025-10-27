"""Repository for interacting with user persistence models."""

from __future__ import annotations

from typing import Sequence

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from ..models import User
from .base import BaseRepository


class UserRepository(BaseRepository[User]):
    """Concrete repository for CRUD operations on ``User`` entities."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, User)

    async def get_by_email(self, email: str) -> User | None:
        """Return a user matching the supplied email if it exists."""
        result = await self.session.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    async def list_active(self) -> list[User]:
        """Return all active users."""
        result = await self.session.execute(select(User).where(User.is_active.is_(True)))
        return list(result.scalars().all())

    async def list_by_ids(self, ids: Sequence[int]) -> list[User]:
        """Fetch all users whose IDs are contained in the provided sequence."""
        if not ids:
            return []
        result = await self.session.execute(select(User).where(User.id.in_(ids)))
        return list(result.scalars().all())
