"""Routes handling user authentication flows."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm

from ...core.config import Settings
from ...deps import DatabaseSessionDependency, SettingsDependency
from ...models import User
from ...schemas import (
    AuthResponse,
    AuthTokens,
    RefreshRequest,
    RefreshResponse,
    SignupRequest,
    UserPublic,
)
from ...services import AuthService
from ...services.auth import TokenPair

router = APIRouter(prefix="/auth", tags=["auth"])


def _build_tokens(token_pair: TokenPair, settings: Settings) -> AuthTokens:
    return AuthTokens(
        access_token=token_pair.access.token,
        refresh_token=token_pair.refresh.token,
        expires_in=settings.access_token_expire_minutes * 60,
        refresh_expires_in=settings.refresh_token_expire_minutes * 60,
    )


def _map_user(user: User) -> UserPublic:
    return UserPublic.model_validate(user)


@router.post(
    "/signup",
    response_model=AuthResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user account",
)
async def signup(
    payload: SignupRequest,
    session: DatabaseSessionDependency,
    settings: SettingsDependency,
) -> AuthResponse:
    service = AuthService(session, settings)
    user = await service.register_user(
        email=payload.email,
        password=payload.password,
        full_name=payload.full_name,
    )

    token_pair = service.build_token_pair(user)
    return AuthResponse(user=_map_user(user), tokens=_build_tokens(token_pair, settings))


@router.post(
    "/login",
    response_model=AuthResponse,
    status_code=status.HTTP_200_OK,
    summary="Authenticate using email and password",
)
async def login(
    session: DatabaseSessionDependency,
    settings: SettingsDependency,
    form_data: OAuth2PasswordRequestForm = Depends(),
) -> AuthResponse:
    service = AuthService(session, settings)
    user = await service.authenticate_user(form_data.username, form_data.password)

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token_pair = service.build_token_pair(user)
    return AuthResponse(user=_map_user(user), tokens=_build_tokens(token_pair, settings))


@router.post(
    "/refresh",
    response_model=RefreshResponse,
    status_code=status.HTTP_200_OK,
    summary="Refresh access credentials using a refresh token",
)
async def refresh_tokens(
    payload: RefreshRequest,
    session: DatabaseSessionDependency,
    settings: SettingsDependency,
) -> RefreshResponse:
    service = AuthService(session, settings)
    user, token_pair = await service.refresh_from_token(payload.refresh_token)

    return RefreshResponse(user=_map_user(user), tokens=_build_tokens(token_pair, settings))
