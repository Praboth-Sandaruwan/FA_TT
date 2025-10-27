"""Database session management utilities."""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from ..core.config import get_settings

settings = get_settings()

engine: AsyncEngine = create_async_engine(
    settings.database_url,
    echo=settings.db_echo,
    pool_pre_ping=True,
)
async_session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    """Yield an ``AsyncSession`` for request-scoped work."""
    async with async_session_maker() as session:
        yield session


async def init_db() -> None:
    """Create all database tables (primarily for tests and local development)."""
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
