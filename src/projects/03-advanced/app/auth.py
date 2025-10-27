"""Authentication helpers for realtime connections."""

from __future__ import annotations

from typing import Mapping

from fastapi import HTTPException, Request, status
from starlette.websockets import WebSocket

from .config import Settings

UNAUTHORIZED_CLOSE_CODE = 4401


class RealtimeAuthenticationError(RuntimeError):
    """Raised when a realtime connection fails authentication."""


def _extract_authorization_token(headers: Mapping[str, str]) -> str | None:
    """Pull a bearer token out of the provided header mapping."""

    auth = headers.get("authorization") or headers.get("Authorization")
    if not auth:
        return None
    scheme, _, token = auth.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    return token.strip()


def require_http_token(request: Request, settings: Settings) -> str:
    """Validate the realtime token for HTTP endpoints such as SSE."""

    token = request.query_params.get("token")
    if not token:
        token = _extract_authorization_token(request.headers)
    if not token or token != settings.realtime_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing realtime token.",
        )
    return token


async def authenticate_websocket(websocket: WebSocket, settings: Settings) -> str:
    """Authenticate an incoming websocket connection by inspecting query and headers."""

    token = websocket.query_params.get("token")
    if not token:
        token = _extract_authorization_token(websocket.headers)
    if not token or token != settings.realtime_token:
        await websocket.close(code=UNAUTHORIZED_CLOSE_CODE)
        raise RealtimeAuthenticationError("Invalid realtime token.")
    return token
