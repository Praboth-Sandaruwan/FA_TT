"""Request-scoped context helpers."""

from __future__ import annotations

from contextvars import ContextVar, Token

REQUEST_ID_HEADER = "X-Request-ID"

_request_id_ctx_var: ContextVar[str] = ContextVar("request_id", default="-")


def get_request_id() -> str:
    """Return the request identifier for the current execution context."""

    return _request_id_ctx_var.get()


def bind_request_id(request_id: str) -> Token[str]:
    """Bind a request identifier to the current execution context."""

    return _request_id_ctx_var.set(request_id)


def reset_request_id(token: Token[str]) -> None:
    """Reset the request identifier using the provided context token."""

    _request_id_ctx_var.reset(token)


def clear_request_id() -> None:
    """Explicitly clear any request identifier from the current context."""

    _request_id_ctx_var.set("-")


__all__ = [
    "REQUEST_ID_HEADER",
    "bind_request_id",
    "clear_request_id",
    "get_request_id",
    "reset_request_id",
]
