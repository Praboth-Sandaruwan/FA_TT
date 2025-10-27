"""Centralised logging configuration for the beginner application."""

from __future__ import annotations

import logging
import logging.config
from typing import Any

from .config import Settings
from .context import get_request_id

_LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(request_id)s | %(message)s"


class RequestContextFilter(logging.Filter):
    """Attach request correlation identifiers to emitted log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id()
        return True


def configure_logging(settings: Settings) -> None:
    """Apply a structured logging configuration using the provided settings."""
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    config: dict[str, Any] = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "standard": {
                "format": _LOG_FORMAT,
                "datefmt": "%Y-%m-%d %H:%M:%S",
            }
        },
        "filters": {
            "request_context": {"()": RequestContextFilter},
        },
        "handlers": {
            "default": {
                "class": "logging.StreamHandler",
                "formatter": "standard",
                "level": level,
                "filters": ["request_context"],
            }
        },
        "loggers": {
            "": {"handlers": ["default"], "level": level},
            "uvicorn": {"handlers": ["default"], "level": level, "propagate": False},
            "uvicorn.error": {
                "handlers": ["default"],
                "level": level,
                "propagate": False,
            },
            "uvicorn.access": {
                "handlers": ["default"],
                "level": level,
                "propagate": False,
            },
        },
    }
    logging.config.dictConfig(config)
