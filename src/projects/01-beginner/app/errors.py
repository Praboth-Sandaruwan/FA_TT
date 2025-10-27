"""Domain specific exception types."""

from __future__ import annotations

from fastapi import HTTPException, status

__all__ = ["ApplicationError", "application_error_to_http"]


class ApplicationError(Exception):
    """Base exception for predictable application errors."""

    def __init__(self, detail: str, *, status_code: int = status.HTTP_400_BAD_REQUEST) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code

    def to_http_exception(self) -> HTTPException:
        """Convert the error into a FastAPI :class:`HTTPException`."""
        return HTTPException(status_code=self.status_code, detail=self.detail)


def application_error_to_http(error: ApplicationError) -> HTTPException:
    """Convenience helper for raising :class:`HTTPException` instances."""
    return error.to_http_exception()
