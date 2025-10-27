"""Schemas describing authentication payloads."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from ..core.security import TokenType
from .user import UserPublic


class SignupRequest(BaseModel):
    """Incoming payload for registering a new user."""

    email: EmailStr
    password: str = Field(min_length=8)
    full_name: str | None = None


class RefreshRequest(BaseModel):
    """Request payload for refreshing JWT tokens."""

    refresh_token: str


class AuthTokens(BaseModel):
    """Access and refresh tokens returned to clients."""

    access_token: str
    refresh_token: str
    token_type: str = Field(default="bearer", frozen=True)
    expires_in: int
    refresh_expires_in: int


class AuthResponse(BaseModel):
    """Authentication response containing issued tokens and user metadata."""

    user: UserPublic
    tokens: AuthTokens


class RefreshResponse(BaseModel):
    """Response payload for a refresh request."""

    user: UserPublic
    tokens: AuthTokens


class TokenPayload(BaseModel):
    """Validated JWT payload."""

    model_config = ConfigDict(extra="ignore")

    sub: str
    exp: datetime
    iat: datetime
    jti: str
    roles: list[str]
    type: TokenType


__all__ = [
    "AuthResponse",
    "AuthTokens",
    "RefreshRequest",
    "RefreshResponse",
    "SignupRequest",
    "TokenPayload",
]
