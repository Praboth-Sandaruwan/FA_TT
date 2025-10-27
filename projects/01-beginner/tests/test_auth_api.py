from __future__ import annotations

import pytest
from httpx import AsyncClient
from jose import jwt
from typing import Callable
from importlib import import_module

BEGINNER_PACKAGE = "projects.01-beginner"


def load_beginner_module(path: str):
    return import_module(f"{BEGINNER_PACKAGE}.{path}")

config_module = load_beginner_module("app.core.config")
models_module = load_beginner_module("app.models")
security_module = load_beginner_module("app.core.security")

get_settings = getattr(config_module, "get_settings")
TokenType = getattr(security_module, "TokenType")
decode_token = getattr(security_module, "decode_token")
UserRole = getattr(models_module, "UserRole")

pytestmark = pytest.mark.asyncio


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
    refreshed_tokens = refresh_response.json()["tokens"]
    assert refreshed_tokens["access_token"] != login_tokens["access_token"]
    assert refreshed_tokens["refresh_token"] != login_tokens["refresh_token"]

    reuse_response = await client.post(
        "/api/auth/refresh",
        json={"refresh_token": login_tokens["refresh_token"]},
    )
    assert reuse_response.status_code == 401
    assert reuse_response.json()["detail"] == "Refresh token has been revoked."

    me_response = await client.get(
        "/api/users/me",
        headers={"Authorization": f"Bearer {refreshed_tokens['access_token']}"},
    )
    assert me_response.status_code == 200
    assert me_response.json()["email"] == signup_payload["email"]


async def test_login_invalid_credentials(client: AsyncClient) -> None:
    response = await client.post(
        "/api/auth/login",
        data={"username": "unknown@example.com", "password": "doesnotmatter"},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Incorrect email or password."


async def test_signup_duplicate_email(client: AsyncClient) -> None:
    payload = {
        "email": "duplicate@example.com",
        "password": "AnotherStrongPass123!",
        "full_name": "Duplicate User",
    }
    first = await client.post("/api/auth/signup", json=payload)
    assert first.status_code == 201

    second = await client.post("/api/auth/signup", json=payload)
    assert second.status_code == 400
    assert second.json()["detail"] == "Email is already registered."


async def test_login_inactive_user(client: AsyncClient, authenticated_user: Callable[..., "AuthenticatedUser"]) -> None:
    inactive_user = await authenticated_user(is_active=False, login=False)

    response = await client.post(
        "/api/auth/login",
        data={"username": inactive_user.email, "password": inactive_user.password},
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "User account is inactive."


async def test_protected_routes_require_correct_roles(
    client: AsyncClient,
    authenticated_user: Callable[..., "AuthenticatedUser"],
) -> None:
    admin = await authenticated_user(role=UserRole.ADMIN)
    regular_user = await authenticated_user()

    admin_response = await client.get("/api/users/admin", headers=admin.headers)
    assert admin_response.status_code == 200
    assert admin_response.json()["email"] == admin.email

    forbidden_response = await client.get("/api/users/admin", headers=regular_user.headers)
    assert forbidden_response.status_code == 403
    assert forbidden_response.json()["detail"] == "Not enough permissions."

    unauthenticated_response = await client.get("/api/users/me")
    assert unauthenticated_response.status_code == 401
    assert unauthenticated_response.json()["detail"] == "Could not validate credentials."


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


async def test_refresh_rejects_access_token(
    client: AsyncClient,
    authenticated_user: Callable[..., "AuthenticatedUser"],
) -> None:
    user = await authenticated_user()
    settings = get_settings()
    payload = decode_token(
        token=user.refresh_token,
        secret=settings.jwt_refresh_secret_key,
        algorithm=settings.jwt_algorithm,
    )
    payload["type"] = TokenType.ACCESS.value
    forged_token = jwt.encode(payload, settings.jwt_refresh_secret_key, algorithm=settings.jwt_algorithm)

    response = await client.post(
        "/api/auth/refresh",
        json={"refresh_token": forged_token},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid token type for refresh."
