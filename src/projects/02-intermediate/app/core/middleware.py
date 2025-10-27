"""Application middleware implementations."""

from __future__ import annotations

import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from .context import REQUEST_ID_HEADER, bind_request_id, reset_request_id


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Attach a correlation identifier to each request/response cycle."""

    def __init__(self, app, header_name: str = REQUEST_ID_HEADER):  # type: ignore[override]
        super().__init__(app)
        self._header_name = header_name

    async def dispatch(self, request: Request, call_next) -> Response:  # type: ignore[override]
        request_id = request.headers.get(self._header_name) or self._generate_request_id()
        token = bind_request_id(request_id)
        request.state.request_id = request_id
        try:
            response = await call_next(request)
        finally:
            reset_request_id(token)
        response.headers.setdefault(self._header_name, request_id)
        return response

    @staticmethod
    def _generate_request_id() -> str:
        return str(uuid.uuid4())


__all__ = ["CorrelationIdMiddleware"]
