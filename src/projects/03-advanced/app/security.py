"""Security utilities for the advanced realtime FastAPI application."""

from __future__ import annotations

from typing import Awaitable, Callable, Mapping

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Apply hardened security headers consistently across HTTP responses."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        headers: Mapping[str, str | None],
        remove_server_header: bool = True,
    ) -> None:
        super().__init__(app)
        self._headers = {key: value for key, value in headers.items() if value}
        self._remove_server_header = remove_server_header

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        response = await call_next(request)
        for header, value in self._headers.items():
            if header.lower() == "content-security-policy":
                response.headers[header] = value
                continue
            response.headers.setdefault(header, value)
        if self._remove_server_header:
            response.headers.pop("server", None)
        return response
