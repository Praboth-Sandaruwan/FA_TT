"""Centralised logging configuration for the application."""

from __future__ import annotations

import logging
from logging.config import dictConfig
from typing import Any

from .config import Settings

__all__ = ["configure_logging"]

_LOGGING_CONFIGURED = False
_LOGGING_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"


def _build_logging_config(level: str) -> dict[str, Any]:
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "standard": {
                "format": _LOGGING_FORMAT,
            }
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "standard",
                "level": level,
            }
        },
        "loggers": {
            "": {
                "handlers": ["console"],
                "level": level,
            }
        },
    }


def configure_logging(settings: Settings) -> None:
    """Configure structured logging based on the provided settings."""
    global _LOGGING_CONFIGURED

    if _LOGGING_CONFIGURED:
        return

    dictConfig(_build_logging_config(settings.log_level.upper()))
    logging.getLogger(__name__).debug("Logging configured")
    _LOGGING_CONFIGURED = True
