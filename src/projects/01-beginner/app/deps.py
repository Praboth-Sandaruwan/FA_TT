"""Shared FastAPI dependency definitions."""

from __future__ import annotations

from .core.config import Settings, get_settings

__all__ = ["get_settings_dependency"]


def get_settings_dependency() -> Settings:
    """Expose the application settings as a dependency."""
    return get_settings()
