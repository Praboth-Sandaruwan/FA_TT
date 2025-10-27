"""Base repository implementation supporting asynchronous SQLModel sessions."""

from __future__ import annotations

from typing import Generic, TypeVar

from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession

ModelType = TypeVar("ModelType", bound=SQLModel)


class BaseRepository(Generic[ModelType]):
    """Provide shared persistence helpers for repositories."""

    def __init__(self, session: AsyncSession, model_type: type[ModelType]) -> None:
        self._session = session
        self._model_type = model_type

    @property
    def session(self) -> AsyncSession:
        """Return the session associated with the repository."""
        return self._session

    async def get(self, entity_id: int) -> ModelType | None:
        """Retrieve a model instance by its primary key."""
        return await self._session.get(self._model_type, entity_id)

    async def list(self) -> list[ModelType]:
        """Return all entities of the repository type."""
        result = await self._session.execute(select(self._model_type))
        return list(result.scalars().all())

    async def add(self, instance: ModelType) -> ModelType:
        """Add and flush a new entity instance."""
        self._session.add(instance)
        await self._session.flush()
        return instance

    async def delete(self, instance: ModelType) -> None:
        """Delete an entity instance and flush the change."""
        await self._session.delete(instance)
        await self._session.flush()

    async def refresh(self, instance: ModelType) -> ModelType:
        """Refresh an entity from the database and return it."""
        await self._session.refresh(instance)
        return instance
