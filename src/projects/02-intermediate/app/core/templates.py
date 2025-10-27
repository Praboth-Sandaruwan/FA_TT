from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import Request
from fastapi.templating import Jinja2Templates

from .session import ensure_csrf_token, pop_flash_messages

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"

_templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
_templates.env.globals.setdefault("htmx_version", "1.9.12")


def is_htmx_request(request: Request) -> bool:
    """Return ``True`` when the incoming request originated from HTMX."""

    return request.headers.get("HX-Request", "").lower() == "true"


def _base_context(
    request: Request,
    extra: dict[str, Any] | None = None,
    *,
    include_messages: bool = True,
) -> dict[str, Any]:
    context = dict(extra or {})
    session = request.session

    context.setdefault("request", request)
    context.setdefault("settings", getattr(request.app.state, "settings", None))
    context.setdefault("current_user", None)
    context["csrf_token"] = ensure_csrf_token(session)
    context["is_htmx"] = is_htmx_request(request)

    if include_messages:
        context["messages"] = pop_flash_messages(session)
    else:
        context.setdefault("messages", [])

    return context


def template_response(
    request: Request,
    template_name: str,
    context: dict[str, Any] | None = None,
    *,
    status_code: int = 200,
) -> Any:
    """Render a full HTML response using the shared template environment."""

    payload = _base_context(request, context, include_messages=True)
    return _templates.TemplateResponse(template_name, payload, status_code=status_code)


def partial_response(
    request: Request,
    template_name: str,
    context: dict[str, Any] | None = None,
    *,
    status_code: int = 200,
) -> Any:
    """Render a fragment without consuming queued flash messages."""

    payload = _base_context(request, context, include_messages=False)
    return _templates.TemplateResponse(template_name, payload, status_code=status_code)


__all__ = [
    "TEMPLATES_DIR",
    "is_htmx_request",
    "partial_response",
    "template_response",
]
