from __future__ import annotations

import secrets
from typing import Any, MutableMapping

SESSION_USER_KEY = "user_id"
SESSION_CSRF_KEY = "csrf_token"
SESSION_FLASH_KEY = "flash_messages"


def get_session_user_id(session: MutableMapping[str, Any]) -> int | None:
    """Return the authenticated user's identifier stored in the session."""

    raw = session.get(SESSION_USER_KEY)
    if raw is None:
        return None
    if isinstance(raw, int):
        return raw
    try:
        return int(str(raw))
    except (TypeError, ValueError):  # pragma: no cover - defensive guard
        return None


def login_user(session: MutableMapping[str, Any], user_id: int) -> None:
    """Persist the authenticated user's identifier in the session."""

    session[SESSION_USER_KEY] = int(user_id)


def logout_user(session: MutableMapping[str, Any]) -> None:
    """Remove user-specific state from the session."""

    session.pop(SESSION_USER_KEY, None)
    session.pop(SESSION_CSRF_KEY, None)
    session.pop(SESSION_FLASH_KEY, None)


def ensure_csrf_token(session: MutableMapping[str, Any]) -> str:
    """Return a CSRF token, generating one if necessary."""

    token = session.get(SESSION_CSRF_KEY)
    if isinstance(token, str) and token:
        return token
    token = secrets.token_urlsafe(32)
    session[SESSION_CSRF_KEY] = token
    return token


def validate_csrf_token(session: MutableMapping[str, Any], provided: str | None) -> bool:
    """Validate a CSRF token against the value stored in the session."""

    expected = session.get(SESSION_CSRF_KEY)
    if not expected or not provided:
        return False
    return secrets.compare_digest(str(expected), str(provided))


def add_flash_message(session: MutableMapping[str, Any], category: str, message: str) -> None:
    """Store a one-time flash message in the session."""

    payload = {
        "category": category,
        "message": message,
    }
    existing = session.get(SESSION_FLASH_KEY)
    if isinstance(existing, list):
        existing.append(payload)
        session[SESSION_FLASH_KEY] = existing
        return
    session[SESSION_FLASH_KEY] = [payload]


def pop_flash_messages(session: MutableMapping[str, Any]) -> list[dict[str, str]]:
    """Retrieve and clear any queued flash messages from the session."""

    messages = session.pop(SESSION_FLASH_KEY, [])
    if not isinstance(messages, list):
        return []
    cleaned: list[dict[str, str]] = []
    for item in messages:
        if not isinstance(item, dict):
            continue
        category = str(item.get("category", "info"))
        message = str(item.get("message", ""))
        if not message:
            continue
        cleaned.append({"category": category, "message": message})
    return cleaned


__all__ = [
    "SESSION_CSRF_KEY",
    "SESSION_FLASH_KEY",
    "SESSION_USER_KEY",
    "add_flash_message",
    "ensure_csrf_token",
    "get_session_user_id",
    "login_user",
    "logout_user",
    "pop_flash_messages",
    "validate_csrf_token",
]
