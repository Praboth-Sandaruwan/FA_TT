"""Reusable FastAPI dependencies."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from typing import Annotated, Awaitable

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError
from pydantic import ValidationError
from sqlmodel.ext.asyncio.session import AsyncSession

from .core.config import Settings, get_settings
from .core.security import TokenType, decode_token, is_token_blacklisted
from .db.session import get_session
from .models import User, UserRole
from .repositories import UserRepository
from .schemas.auth import TokenPayload

SettingsDependency = Annotated[Settings, Depends(get_settings)]
DatabaseSessionDependency = Annotated[AsyncSession, Depends(get_session)]

_oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")


async def get_db_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency that yields a database session."""

    async for session in get_session():
        yield session


def _unauthorized(detail: str = "Could not validate credentials.") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def _forbidden(detail: str = "Not enough permissions.") -> HTTPException:
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


def _decode_access_token(token: str, settings: Settings) -> TokenPayload:
    try:
        payload = decode_token(
            token=token,
            secret=settings.jwt_secret_key,
            algorithm=settings.jwt_algorithm,
        )
    except JWTError as exc:  # pragma: no cover - defensive guard
        raise _unauthorized() from exc

    try:
        token_payload = TokenPayload.model_validate(payload)
    except ValidationError as exc:  # pragma: no cover - defensive guard
        raise _unauthorized() from exc

    if token_payload.type is not TokenType.ACCESS:
        raise _unauthorized("Invalid token type.")
    if is_token_blacklisted(token_payload.jti):
        raise _unauthorized("Token has been revoked.")

    return token_payload


def _role_satisfied(user_role: UserRole, required: UserRole) -> bool:
    if required == UserRole.USER:
        return user_role in {UserRole.USER, UserRole.ADMIN}
    if required == UserRole.ADMIN:
        return user_role == UserRole.ADMIN
    return False


def require_current_user(required_role: UserRole | None = None) -> Callable[..., Awaitable[User]]:
    """Return a dependency enforcing authentication and optional role checks."""

    async def _dependency(
        token: str = Depends(_oauth2_scheme),
        session: AsyncSession = Depends(get_db_session),
        settings: Settings = Depends(get_settings),
    ) -> User:
        token_payload = _decode_access_token(token, settings)
        try:
            user_id = int(token_payload.sub)
        except ValueError as exc:  # pragma: no cover - defensive guard
            raise _unauthorized() from exc

        repository = UserRepository(session)
        user = await repository.get(user_id)
        if user is None:
            raise _unauthorized()
        if not user.is_active:
            raise _forbidden("User account is inactive.")
        if required_role is not None and not _role_satisfied(
            user.role,
            required_role,
        ):
            raise _forbidden()
        return user

    return _dependency


CurrentUserDependency = Annotated[User, Depends(require_current_user())]
AdminUserDependency = Annotated[User, Depends(require_current_user(UserRole.ADMIN))]


__all__ = [
    "AdminUserDependency",
    "CurrentUserDependency",
    "DatabaseSessionDependency",
    "SettingsDependency",
    "get_db_session",
    "require_current_user",
]
