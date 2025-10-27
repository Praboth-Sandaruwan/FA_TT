"""Application-level exception handling helpers."""

from __future__ import annotations

from fastapi import FastAPI, status
from fastapi.responses import JSONResponse
from starlette.requests import Request


class ApplicationError(Exception):
    """Base class for domain-specific errors."""

    def __init__(self, detail: str, *, status_code: int = status.HTTP_400_BAD_REQUEST) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


def register_exception_handlers(app: FastAPI) -> None:
    """Register exception handlers with the provided FastAPI app."""

    @app.exception_handler(ApplicationError)
    async def _handle_application_error(request: Request, exc: ApplicationError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


__all__ = ["ApplicationError", "register_exception_handlers"]
