"""Reusable FastAPI dependencies."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends
from sqlmodel.ext.asyncio.session import AsyncSession

from .core.config import Settings, get_settings
from .db.session import get_session

SettingsDependency = Annotated[Settings, Depends(get_settings)]
DatabaseSessionDependency = Annotated[AsyncSession, Depends(get_session)]


async def get_db_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency that yields a database session."""
    async for session in get_session():
        yield session
