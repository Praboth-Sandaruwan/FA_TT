from __future__ import annotations

import sys
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from itertools import count
from importlib import import_module
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest_asyncio
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel

BEGINNER_PACKAGE = "projects.01-beginner"
PROJECT_ROOT = Path(__file__).resolve().parents[3] / "src" / "projects" / "01-beginner"


def _ensure_beginner_package() -> None:
    if BEGINNER_PACKAGE in sys.modules:
        return
    spec = spec_from_file_location(
        BEGINNER_PACKAGE,
        PROJECT_ROOT / "__init__.py",
        submodule_search_locations=[str(PROJECT_ROOT)],
    )
    module = module_from_spec(spec)
    sys.modules[BEGINNER_PACKAGE] = module
    spec.loader.exec_module(module)
    parent = import_module("projects")
    setattr(parent, "01-beginner", module)


_ensure_beginner_package()

try:  # pragma: no cover - provide a stub when uvicorn is unavailable
    import uvicorn  # noqa: F401
except ModuleNotFoundError:  # pragma: no cover - exercised only in test envs without uvicorn
    stub = ModuleType("uvicorn")

    def _run(*_: object, **__: object) -> None:
        raise RuntimeError("uvicorn.run should not be invoked during tests.")

    stub.run = _run  # type: ignore[attr-defined]
    sys.modules["uvicorn"] = stub

config_module = import_module(f"{BEGINNER_PACKAGE}.app.core.config")
deps_module = import_module(f"{BEGINNER_PACKAGE}.app.deps")
main_module = import_module(f"{BEGINNER_PACKAGE}.app.main")
models_module = import_module(f"{BEGINNER_PACKAGE}.app.models")
services_module = import_module(f"{BEGINNER_PACKAGE}.app.services")

get_settings = getattr(config_module, "get_settings")
get_db_session = getattr(deps_module, "get_db_session")
create_app = getattr(main_module, "create_app")
User = getattr(models_module, "User")
UserRole = getattr(models_module, "UserRole")
UserService = getattr(services_module, "UserService")


@dataclass(slots=True)
class AuthenticatedUser:
    user: User
    email: str
    password: str
    tokens: dict[str, str] | None

    @property
    def id(self) -> int:
        if self.user.id is None:  # pragma: no cover - defensive guard
            raise RuntimeError("Persisted user is missing an id.")
        return self.user.id

    @property
    def headers(self) -> dict[str, str]:
        if not self.tokens:
            raise RuntimeError("User has not been authenticated.")
        return {"Authorization": f"Bearer {self.tokens['access_token']}"}

    @property
    def access_token(self) -> str:
        if not self.tokens:
            raise RuntimeError("User has not been authenticated.")
        return self.tokens["access_token"]

    @property
    def refresh_token(self) -> str:
        if not self.tokens:
            raise RuntimeError("User has not been authenticated.")
        return self.tokens["refresh_token"]


@pytest_asyncio.fixture(scope="session")
async def engine() -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def session(engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    async_session_factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with engine.connect() as connection:
        transaction = await connection.begin()
        session = async_session_factory(bind=connection)
        sync_session = session.sync_session
        await connection.begin_nested()

        @event.listens_for(sync_session, "after_transaction_end")
        def restart_savepoint(session_: Any, transaction_: Any) -> None:
            connection = getattr(transaction_, "connection", None)
            if getattr(transaction_, "nested", False) and connection is not None and not connection.closed:
                session_.begin_nested()

        try:
            yield session
        finally:
            event.remove(sync_session, "after_transaction_end", restart_savepoint)
            await session.close()
            await transaction.rollback()


@pytest_asyncio.fixture
async def app(session: AsyncSession) -> AsyncIterator[FastAPI]:
    get_settings.cache_clear()
    settings = get_settings()
    original_access = settings.access_token_expire_minutes
    original_refresh = settings.refresh_token_expire_minutes

    application = create_app()

    async def _override_db_session() -> AsyncIterator[AsyncSession]:
        yield session

    application.dependency_overrides[get_db_session] = _override_db_session
    settings.access_token_expire_minutes = 5
    settings.refresh_token_expire_minutes = 60
    try:
        yield application
    finally:
        application.dependency_overrides.clear()
        settings.access_token_expire_minutes = original_access
        settings.refresh_token_expire_minutes = original_refresh


@pytest_asyncio.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(app=app, base_url="http://testserver") as http_client:
        yield http_client


@pytest_asyncio.fixture
async def authenticated_user(
    session: AsyncSession,
    client: AsyncClient,
) -> AsyncIterator[Callable[..., AuthenticatedUser]]:
    user_service = UserService(session)
    counter = count()

    async def _factory(
        *,
        email: str | None = None,
        password: str = "StrongPass123!",
        full_name: str | None = None,
        role: UserRole = UserRole.USER,
        is_active: bool = True,
        login: bool = True,
    ) -> AuthenticatedUser:
        actual_email = email or f"user-{next(counter)}@example.com"
        user = await user_service.create_user(
            email=actual_email,
            password=password,
            full_name=full_name,
            is_active=is_active,
            role=role,
        )
        tokens: dict[str, str] | None = None
        if login:
            response = await client.post(
                "/api/auth/login",
                data={"username": actual_email, "password": password},
            )
            assert response.status_code == 200, response.text
            tokens = response.json()["tokens"]
        return AuthenticatedUser(
            user=user,
            email=actual_email,
            password=password,
            tokens=tokens,
        )

    yield _factory
