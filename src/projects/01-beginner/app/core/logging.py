"""Centralised logging configuration for the beginner application."""

from __future__ import annotations

import logging
import logging.config
from typing import Any

from .config import Settings

_LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"


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
        "handlers": {
            "default": {
                "class": "logging.StreamHandler",
                "formatter": "standard",
                "level": level,
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
