"""Application-level exception handling helpers."""

from __future__ import annotations

import logging
from contextvars import Token
from http import HTTPStatus
from typing import Any, Mapping

from fastapi import FastAPI, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.requests import Request

from .core.context import REQUEST_ID_HEADER, bind_request_id, reset_request_id
from .schemas.system import ErrorResponse

logger = logging.getLogger(__name__)


class ApplicationError(Exception):
    """Base class for domain-specific errors."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "application_error",
        status_code: int = status.HTTP_400_BAD_REQUEST,
        details: Any | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.detail = message
        self.code = code
        self.status_code = status_code
        self.details = details


class NotFoundError(ApplicationError):
    """Error representing missing resources."""

    def __init__(
        self,
        message: str = "Resource not found.",
        *,
        code: str = "not_found",
        details: Any | None = None,
    ) -> None:
        super().__init__(
            message,
            code=code,
            status_code=status.HTTP_404_NOT_FOUND,
            details=details,
        )


class ValidationError(ApplicationError):
    """Error representing business validation failures."""

    def __init__(
        self,
        message: str = "Validation failed.",
        *,
        code: str = "validation_error",
        details: Any | None = None,
    ) -> None:
        super().__init__(
            message,
            code=code,
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            details=details,
        )


class DatabaseIntegrityError(ApplicationError):
    """Error representing database integrity violations."""

    def __init__(
        self,
        message: str = "Database integrity violation.",
        *,
        code: str = "db_integrity_error",
        details: Any | None = None,
    ) -> None:
        super().__init__(
            message,
            code=code,
            status_code=status.HTTP_409_CONFLICT,
            details=details,
        )


class ServerError(ApplicationError):
    """Error representing unexpected server failures."""

    def __init__(
        self,
        message: str = "Internal server error.",
        *,
        code: str = "server_error",
        details: Any | None = None,
    ) -> None:
        super().__init__(
            message,
            code=code,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            details=details,
        )


_HTTP_STATUS_CODE_MAP: dict[int, str] = {
    status.HTTP_400_BAD_REQUEST: "bad_request",
    status.HTTP_401_UNAUTHORIZED: "unauthorized",
    status.HTTP_403_FORBIDDEN: "forbidden",
    status.HTTP_404_NOT_FOUND: "not_found",
    status.HTTP_405_METHOD_NOT_ALLOWED: "method_not_allowed",
    status.HTTP_409_CONFLICT: "conflict",
    status.HTTP_429_TOO_MANY_REQUESTS: "rate_limited",
}


def _bind_request_context(request: Request) -> Token[str] | None:
    request_id = getattr(request.state, "request_id", None)
    if not request_id:
        return None
    return bind_request_id(request_id)


def _reset_request_context(token: Token[str] | None) -> None:
    if token is not None:
        reset_request_id(token)


def _normalize_details(raw: Any) -> Any | None:
    if raw is None:
        return None
    if isinstance(raw, list):
        return {"errors": raw}
    return raw


def _merge_details_with_request(request: Request, details: Any | None) -> Any | None:
    request_id = getattr(request.state, "request_id", None)
    if not request_id:
        return details
    if details is None:
        return {"request_id": request_id}
    if isinstance(details, dict):
        if "request_id" not in details:
            return {**details, "request_id": request_id}
        return details
    return {"request_id": request_id, "detail": details}


def _error_response(
    request: Request,
    *,
    status_code: int,
    code: str,
    message: str,
    details: Any | None = None,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    payload = ErrorResponse(
        code=code,
        message=message,
        details=_merge_details_with_request(request, details),
    )
    response = JSONResponse(status_code=status_code, content=payload.model_dump())
    if headers:
        response.headers.update(headers)
    request_id = getattr(request.state, "request_id", None)
    if request_id:
        response.headers.setdefault(REQUEST_ID_HEADER, request_id)
    return response


def _http_exception_details(
    status_code: int,
    detail: Any,
) -> tuple[str, Any | None]:
    if isinstance(detail, str):
        return detail, None
    try:
        status_phrase = HTTPStatus(status_code).phrase
    except ValueError:
        status_phrase = "Error"
    if detail is None:
        return status_phrase, None
    return status_phrase, _normalize_details(detail)


def register_exception_handlers(app: FastAPI) -> None:
    """Register exception handlers with the provided FastAPI app."""

    @app.exception_handler(ApplicationError)
    async def _handle_application_error(
        request: Request,
        exc: ApplicationError,
    ) -> JSONResponse:
        token = _bind_request_context(request)
        try:
            log = logger.error if exc.status_code >= status.HTTP_500_INTERNAL_SERVER_ERROR else logger.warning
            log(
                "Application error encountered",
                extra={"code": exc.code, "status_code": exc.status_code},
            )
            return _error_response(
                request,
                status_code=exc.status_code,
                code=exc.code,
                message=exc.message,
                details=exc.details,
            )
        finally:
            _reset_request_context(token)

    @app.exception_handler(RequestValidationError)
    async def _handle_request_validation_error(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        token = _bind_request_context(request)
        try:
            logger.warning(
                "Request validation failed",
                extra={"errors": exc.errors()},
            )
            return _error_response(
                request,
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                code="validation_error",
                message="Request validation failed.",
                details={"errors": exc.errors()},
            )
        finally:
            _reset_request_context(token)

    @app.exception_handler(IntegrityError)
    async def _handle_integrity_error(
        request: Request,
        exc: IntegrityError,
    ) -> JSONResponse:
        token = _bind_request_context(request)
        try:
            logger.error("Database integrity error encountered.", exc_info=exc)
            return _error_response(
                request,
                status_code=status.HTTP_409_CONFLICT,
                code="db_integrity_error",
                message="Database integrity violation.",
            )
        finally:
            _reset_request_context(token)

    @app.exception_handler(StarletteHTTPException)
    async def _handle_http_exception(
        request: Request,
        exc: StarletteHTTPException,
    ) -> JSONResponse:
        token = _bind_request_context(request)
        try:
            code = _HTTP_STATUS_CODE_MAP.get(exc.status_code, "http_error")
            message, extra_details = _http_exception_details(exc.status_code, exc.detail)
            log = logger.error if exc.status_code >= status.HTTP_500_INTERNAL_SERVER_ERROR else logger.warning
            log(
                "HTTP exception raised",
                extra={"code": code, "status_code": exc.status_code, "path": str(request.url.path)},
            )
            headers = exc.headers or None
            return _error_response(
                request,
                status_code=exc.status_code,
                code=code,
                message=message,
                details=extra_details,
                headers=headers,
            )
        finally:
            _reset_request_context(token)

    @app.exception_handler(Exception)
    async def _handle_unhandled_exception(
        request: Request,
        exc: Exception,
    ) -> JSONResponse:
        token = _bind_request_context(request)
        try:
            logger.exception("Unhandled application error.")
            return _error_response(
                request,
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                code="server_error",
                message="Internal server error.",
            )
        finally:
            _reset_request_context(token)


__all__ = [
    "ApplicationError",
    "DatabaseIntegrityError",
    "NotFoundError",
    "ServerError",
    "ValidationError",
    "register_exception_handlers",
]
