"""Service layer orchestrating user-related repository operations."""

from __future__ import annotations

from typing import Sequence

from sqlmodel.ext.asyncio.session import AsyncSession

from ..core.security import get_password_hash
from ..models import User, UserRole
from ..repositories import UserRepository


class UserService:
    """High-level business operations for ``User`` entities."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repository = UserRepository(session)

    @property
    def repository(self) -> UserRepository:
        """Expose the underlying repository for advanced scenarios."""
        return self._repository

    async def create_user(
        self,
        *,
        email: str,
        password: str,
        full_name: str | None = None,
        is_active: bool = True,
        role: UserRole = UserRole.USER,
    ) -> User:
        """Create and persist a new user record."""
        hashed_password = get_password_hash(password)
        user = User(
            email=email,
            full_name=full_name,
            is_active=is_active,
            role=role,
            hashed_password=hashed_password,
        )
        await self._repository.add(user)
        await self._session.commit()
        await self._repository.refresh(user)
        return user

    async def get_user(self, user_id: int) -> User | None:
        """Fetch a user by primary key."""
        return await self._repository.get(user_id)

    async def get_user_by_email(self, email: str) -> User | None:
        """Fetch a user by their unique email address."""
        return await self._repository.get_by_email(email)

    async def list_users(self) -> list[User]:
        """Return all registered users."""
        return await self._repository.list()

    async def list_active_users(self) -> list[User]:
        """Return all users flagged as active."""
        return await self._repository.list_active()

    async def list_users_by_ids(self, ids: Sequence[int]) -> list[User]:
        """Retrieve users whose identifiers match the provided sequence."""
        return await self._repository.list_by_ids(ids)

    async def update_user(
        self,
        user_id: int,
        *,
        full_name: str | None = None,
        is_active: bool | None = None,
        role: UserRole | None = None,
        password: str | None = None,
    ) -> User:
        """Apply updates to a user record and persist the changes."""
        user = await self._repository.get(user_id)
        if user is None:
            raise ValueError(f"User {user_id} does not exist")
        if full_name is not None:
            user.full_name = full_name
        if is_active is not None:
            user.is_active = is_active
        if role is not None:
            user.role = role
        if password is not None:
            user.hashed_password = get_password_hash(password)
        await self._session.commit()
        await self._repository.refresh(user)
        return user

    async def delete_user(self, user_id: int) -> bool:
        """Delete a user by ID, returning ``True`` if a record was removed."""
        user = await self._repository.get(user_id)
        if user is None:
            return False
        await self._repository.delete(user)
        await self._session.commit()
        return True
