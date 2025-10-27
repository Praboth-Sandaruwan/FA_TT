"""Authentication service encapsulating user registration and token flows."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timezone

from fastapi import status
from jose import ExpiredSignatureError, JWTError
from sqlmodel.ext.asyncio.session import AsyncSession

from ..core.config import Settings
from ..core.security import (
    GeneratedToken,
    TokenType,
    blacklist_token,
    create_access_token,
    create_refresh_token,
    decode_token,
    is_token_blacklisted,
    verify_password,
)
from ..errors import ApplicationError
from ..models import User, UserRole
from ..repositories import UserRepository
from ..schemas.auth import TokenPayload
from .users import UserService


@dataclass(slots=True)
class TokenPair:
    """Container for access and refresh tokens."""

    access: GeneratedToken
    refresh: GeneratedToken


class AuthService:
    """High-level authentication workflows for the intermediate application."""

    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self._session = session
        self._settings = settings
        self._user_service = UserService(session)
        self._user_repository = UserRepository(session)

    async def register_user(
        self,
        *,
        email: str,
        password: str,
        full_name: str | None = None,
    ) -> User:
        existing = await self._user_service.get_user_by_email(email)
        if existing is not None:
            raise ApplicationError(
                "Email is already registered.",
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        return await self._user_service.create_user(
            email=email,
            password=password,
            full_name=full_name,
            is_active=True,
            role=UserRole.USER,
        )

    async def authenticate_user(self, email: str, password: str) -> User | None:
        user = await self._user_service.get_user_by_email(email)
        if user is None:
            return None
        if not verify_password(password, user.hashed_password):
            return None
        if not user.is_active:
            raise ApplicationError(
                "User account is inactive.",
                status_code=status.HTTP_403_FORBIDDEN,
            )
        return user

    def build_token_pair(self, user: User) -> TokenPair:
        if user.id is None:
            raise ApplicationError("User must be persisted before issuing tokens.")
        roles = [user.role.value]
        access = create_access_token(
            subject=user.id,
            roles=roles,
            settings=self._settings,
        )
        refresh = create_refresh_token(
            subject=user.id,
            roles=roles,
            settings=self._settings,
        )
        return TokenPair(access=access, refresh=refresh)

    async def refresh_from_token(self, refresh_token: str) -> tuple[User, TokenPair]:
        try:
            payload_dict = decode_token(
                token=refresh_token,
                secret=self._settings.jwt_refresh_secret_key,
                algorithm=self._settings.jwt_algorithm,
            )
        except ExpiredSignatureError as exc:
            raise ApplicationError(
                "Refresh token has expired.",
                status_code=status.HTTP_401_UNAUTHORIZED,
            ) from exc
        except JWTError as exc:  # pragma: no cover - defensive guard
            raise ApplicationError(
                "Invalid refresh token.",
                status_code=status.HTTP_401_UNAUTHORIZED,
            ) from exc

        token_payload = TokenPayload.model_validate(payload_dict)
        if token_payload.type is not TokenType.REFRESH:
            raise ApplicationError(
                "Invalid token type for refresh.",
                status_code=status.HTTP_401_UNAUTHORIZED,
            )
        if is_token_blacklisted(token_payload.jti):
            raise ApplicationError(
                "Refresh token has been revoked.",
                status_code=status.HTTP_401_UNAUTHORIZED,
            )
        try:
            user_id = int(token_payload.sub)
        except ValueError as exc:  # pragma: no cover - defensive guard
            raise ApplicationError(
                "Invalid token subject.",
                status_code=status.HTTP_401_UNAUTHORIZED,
            ) from exc
        user = await self._user_repository.get(user_id)
        if user is None:
            raise ApplicationError(
                "User no longer exists.",
                status_code=status.HTTP_401_UNAUTHORIZED,
            )
        if not user.is_active:
            raise ApplicationError(
                "User account is inactive.",
                status_code=status.HTTP_403_FORBIDDEN,
            )

        expires_at = token_payload.exp
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        blacklist_token(token_payload.jti, expires_at)

        tokens = self.build_token_pair(user)
        return user, tokens


__all__ = ["AuthService", "TokenPair"]
