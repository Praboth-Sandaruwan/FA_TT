"""Security helpers for password hashing and JWT token management."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from threading import Lock
from typing import Any, Sequence
from uuid import uuid4

from jose import JWTError, jwt
from passlib.context import CryptContext

from .config import Settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class TokenType(str, Enum):
    """Enumerates supported JWT token types."""

    ACCESS = "access"
    REFRESH = "refresh"


@dataclass(slots=True)
class GeneratedToken:
    """Represents a generated JWT token with associated metadata."""

    token: str
    expires_at: datetime
    jti: str


def get_password_hash(password: str) -> str:
    """Return a hashed representation of ``password``."""

    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain password against its hashed counterpart."""

    return pwd_context.verify(plain_password, hashed_password)


def _ensure_roles_sequence(roles: Sequence[str] | None) -> list[str]:
    if not roles:
        return []
    seen: dict[str, None] = {}
    for role in roles:
        if role not in seen:
            seen[role] = None
    return list(seen.keys())


def _create_token(
    *,
    subject: str | int,
    roles: Sequence[str] | None,
    settings: Settings,
    token_type: TokenType,
    expires_delta: timedelta | None = None,
) -> GeneratedToken:
    now = datetime.now(timezone.utc)
    if expires_delta is None:
        minutes = (
            settings.access_token_expire_minutes
            if token_type is TokenType.ACCESS
            else settings.refresh_token_expire_minutes
        )
        expires_delta = timedelta(minutes=minutes)
    expire = now + expires_delta
    payload: dict[str, Any] = {
        "sub": str(subject),
        "iat": now,
        "exp": expire,
        "roles": _ensure_roles_sequence(roles),
        "type": token_type.value,
        "jti": uuid4().hex,
    }
    secret = (
        settings.jwt_secret_key
        if token_type is TokenType.ACCESS
        else settings.jwt_refresh_secret_key
    )
    token = jwt.encode(payload, secret, algorithm=settings.jwt_algorithm)
    return GeneratedToken(token=token, expires_at=expire, jti=payload["jti"])


def create_access_token(
    *,
    subject: str | int,
    roles: Sequence[str] | None,
    settings: Settings,
    expires_delta: timedelta | None = None,
) -> GeneratedToken:
    """Create a signed JWT access token for the provided subject."""

    return _create_token(
        subject=subject,
        roles=roles,
        settings=settings,
        token_type=TokenType.ACCESS,
        expires_delta=expires_delta,
    )


def create_refresh_token(
    *,
    subject: str | int,
    roles: Sequence[str] | None,
    settings: Settings,
    expires_delta: timedelta | None = None,
) -> GeneratedToken:
    """Create a signed JWT refresh token for the provided subject."""

    return _create_token(
        subject=subject,
        roles=roles,
        settings=settings,
        token_type=TokenType.REFRESH,
        expires_delta=expires_delta,
    )


def decode_token(*, token: str, secret: str, algorithm: str) -> dict[str, Any]:
    """Decode a JWT token and return its payload."""

    return jwt.decode(token, secret, algorithms=[algorithm])


class TokenBlacklist:
    """Stores identifiers for revoked tokens until their expiration."""

    def __init__(self) -> None:
        self._revoked: dict[str, datetime] = {}
        self._lock = Lock()

    def add(self, jti: str, expires_at: datetime) -> None:
        with self._lock:
            self._purge_locked(datetime.now(timezone.utc))
            self._revoked[jti] = expires_at

    def is_revoked(self, jti: str) -> bool:
        with self._lock:
            self._purge_locked(datetime.now(timezone.utc))
            return jti in self._revoked

    def _purge_locked(self, current: datetime) -> None:
        expired = [key for key, expiry in self._revoked.items() if expiry <= current]
        for key in expired:
            self._revoked.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._revoked.clear()


_token_blacklist = TokenBlacklist()


def blacklist_token(jti: str, expires_at: datetime) -> None:
    """Register a token identifier as revoked until ``expires_at``."""

    _token_blacklist.add(jti, expires_at)


def is_token_blacklisted(jti: str) -> bool:
    """Return ``True`` if the token identifier has been revoked."""

    return _token_blacklist.is_revoked(jti)


def clear_token_blacklist() -> None:
    """Remove all tracked revoked tokens."""

    _token_blacklist.clear()


__all__ = [
    "GeneratedToken",
    "JWTError",
    "TokenBlacklist",
    "TokenType",
    "blacklist_token",
    "create_access_token",
    "create_refresh_token",
    "decode_token",
    "get_password_hash",
    "is_token_blacklisted",
    "verify_password",
]
