from __future__ import annotations

from importlib import import_module

import pytest
import pytest_asyncio
from collections.abc import AsyncIterator
from fastapi import FastAPI
from httpx import AsyncClient
from jose import jwt
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

BEGINNER_PACKAGE = "projects.01-beginner"


def load_beginner_module(path: str):
    return import_module(f"{BEGINNER_PACKAGE}.{path}")


config_module = load_beginner_module("app.core.config")
deps_module = load_beginner_module("app.deps")
main_module = load_beginner_module("app.main")
models_module = load_beginner_module("app.models")
security_module = load_beginner_module("app.core.security")
services_module = load_beginner_module("app.services")

create_app = getattr(main_module, "create_app")
get_settings = getattr(config_module, "get_settings")
get_db_session = getattr(deps_module, "get_db_session")
UserRole = getattr(models_module, "UserRole")
UserService = getattr(services_module, "UserService")
TokenType = getattr(security_module, "TokenType")


@pytest_asyncio.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    engine: AsyncEngine = create_async_engine(
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
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        try:
            yield session
        finally:
            transaction = session.in_transaction()
            if transaction is not None:
                await session.rollback()


@pytest_asyncio.fixture
async def app(session: AsyncSession) -> AsyncIterator[FastAPI]:
    get_settings.cache_clear()
    settings = get_settings()
    original_access = settings.access_token_expire_minutes
    original_refresh = settings.refresh_token_expire_minutes
    app = create_app()

    async def _override_db_session():
        yield session

    app.dependency_overrides[get_db_session] = _override_db_session
    settings.access_token_expire_minutes = 5
    settings.refresh_token_expire_minutes = 60

    try:
        yield app
    finally:
        app.dependency_overrides.clear()
        settings.access_token_expire_minutes = original_access
        settings.refresh_token_expire_minutes = original_refresh


@pytest_asyncio.fixture
async def client(app) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(app=app, base_url="http://testserver") as client:
        yield client


@pytest.mark.asyncio
async def test_signup_login_refresh_flow(client: AsyncClient) -> None:
    settings = get_settings()
    signup_payload = {
        "email": "jane@example.com",
        "password": "StrongPass123!",
        "full_name": "Jane Example",
    }

    signup_response = await client.post("/api/auth/signup", json=signup_payload)
    assert signup_response.status_code == 201
    signup_json = signup_response.json()

    assert signup_json["user"]["email"] == signup_payload["email"]
    tokens = signup_json["tokens"]
    decoded_access = jwt.decode(
        tokens["access_token"],
        settings.jwt_secret_key,
        algorithms=[settings.jwt_algorithm],
    )
    assert decoded_access["sub"] == str(signup_json["user"]["id"])
    assert decoded_access["type"] == TokenType.ACCESS.value
    assert decoded_access["roles"] == [UserRole.USER.value]

    login_response = await client.post(
        "/api/auth/login",
        data={"username": signup_payload["email"], "password": signup_payload["password"]},
    )
    assert login_response.status_code == 200
    login_tokens = login_response.json()["tokens"]
    assert login_tokens["access_token"] != tokens["access_token"]

    refresh_response = await client.post(
        "/api/auth/refresh",
        json={"refresh_token": login_tokens["refresh_token"]},
    )
    assert refresh_response.status_code == 200
    refreshed = refresh_response.json()["tokens"]
    assert refreshed["access_token"] != login_tokens["access_token"]
    assert refreshed["refresh_token"] != login_tokens["refresh_token"]

    reuse_response = await client.post(
        "/api/auth/refresh",
        json={"refresh_token": login_tokens["refresh_token"]},
    )
    assert reuse_response.status_code == 401
    assert reuse_response.json()["detail"] == "Refresh token has been revoked."

    me_response = await client.get(
        "/api/users/me",
        headers={"Authorization": f"Bearer {refreshed['access_token']}"},
    )
    assert me_response.status_code == 200
    assert me_response.json()["email"] == signup_payload["email"]


@pytest.mark.asyncio
async def test_login_invalid_credentials(client: AsyncClient) -> None:
    response = await client.post(
        "/api/auth/login",
        data={"username": "unknown@example.com", "password": "doesnotmatter"},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Incorrect email or password."


@pytest.mark.asyncio
async def test_protected_routes_require_correct_roles(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    user_service = UserService(session)
    admin_email = "admin@example.com"
    admin_password = "AdminPass123!"
    await user_service.create_user(
        email=admin_email,
        password=admin_password,
        full_name="Admin User",
        role=UserRole.ADMIN,
    )

    login_response = await client.post(
        "/api/auth/login",
        data={"username": admin_email, "password": admin_password},
    )
    assert login_response.status_code == 200
    admin_token = login_response.json()["tokens"]["access_token"]

    admin_response = await client.get(
        "/api/users/admin",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert admin_response.status_code == 200
    assert admin_response.json()["email"] == admin_email

    user_signup = await client.post(
        "/api/auth/signup",
        json={
            "email": "user@example.com",
            "password": "UserPass123!",
            "full_name": "Regular User",
        },
    )
    assert user_signup.status_code == 201
    user_access_token = user_signup.json()["tokens"]["access_token"]

    forbidden_response = await client.get(
        "/api/users/admin",
        headers={"Authorization": f"Bearer {user_access_token}"},
    )
    assert forbidden_response.status_code == 403
    assert forbidden_response.json()["detail"] == "Not enough permissions."

    unauthenticated_response = await client.get("/api/users/me")
    assert unauthenticated_response.status_code == 401
    assert unauthenticated_response.json()["detail"] == "Could not validate credentials."


@pytest.mark.asyncio
async def test_refresh_with_expired_token(client: AsyncClient) -> None:
    settings = get_settings()
    original_refresh = settings.refresh_token_expire_minutes
    settings.refresh_token_expire_minutes = 0
    try:
        signup_response = await client.post(
            "/api/auth/signup",
            json={
                "email": "expired@example.com",
                "password": "ExpiredPass123!",
            },
        )
        assert signup_response.status_code == 201
        refresh_token = signup_response.json()["tokens"]["refresh_token"]

        refresh_response = await client.post(
            "/api/auth/refresh",
            json={"refresh_token": refresh_token},
        )
        assert refresh_response.status_code == 401
        assert refresh_response.json()["detail"] == "Refresh token has expired."
    finally:
        settings.refresh_token_expire_minutes = original_refresh
