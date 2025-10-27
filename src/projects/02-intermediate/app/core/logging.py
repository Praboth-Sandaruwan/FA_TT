"""Centralised logging configuration for the intermediate application."""

from __future__ import annotations

import json
import logging
import logging.config
from datetime import datetime, timezone
from typing import Any

from .config import Settings
from .context import get_request_id

_RESERVED_LOG_RECORD_ATTRS = {
    "name",
    "msg",
    "args",
    "levelname",
    "levelno",
    "pathname",
    "filename",
    "module",
    "exc_info",
    "exc_text",
    "stack_info",
    "lineno",
    "funcName",
    "created",
    "msecs",
    "relativeCreated",
    "thread",
    "threadName",
    "processName",
    "process",
    "message",
}


class JsonLogFormatter(logging.Formatter):
    """Render log records as structured JSON objects."""

    def __init__(
        self,
        *,
        defaults: dict[str, Any] | None = None,
        fmt: str | None = None,
        datefmt: str | None = None,
        style: str = "%",
    ) -> None:
        super().__init__(fmt=fmt, datefmt=datefmt, style=style)
        self._defaults = defaults or {}

    def format(self, record: logging.LogRecord) -> str:  # type: ignore[override]
        payload: dict[str, Any] = dict(self._defaults)
        payload.update(
            {
                "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
                "level": record.levelname,
                "logger": record.name,
                "message": record.getMessage(),
                "request_id": getattr(record, "request_id", "-"),
            }
        )

        for key, value in record.__dict__.items():
            if key in _RESERVED_LOG_RECORD_ATTRS or key == "request_id":
                continue
            payload.setdefault(key, self._coerce_extra(value))

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        if record.stack_info:
            payload["stack"] = self.formatStack(record.stack_info)

        return json.dumps(payload, ensure_ascii=False, default=str)

    @staticmethod
    def _coerce_extra(value: Any) -> Any:
        try:
            json.dumps(value)
        except TypeError:
            return str(value)
        return value


class RequestContextFilter(logging.Filter):
    """Attach request correlation identifiers to emitted log records."""

    def filter(self, record: logging.LogRecord) -> bool:  # type: ignore[override]
        record.request_id = get_request_id()
        return True


def configure_logging(settings: Settings) -> None:
    """Apply a structured logging configuration using the provided settings."""

    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    logging.captureWarnings(True)

    formatter_path = "projects.02-intermediate.app.core.logging.JsonLogFormatter"
    config: dict[str, Any] = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "json": {
                "()": formatter_path,
                "defaults": {
                    "service": settings.project_name,
                    "environment": settings.environment,
                },
            }
        },
        "filters": {
            "request_context": {"()": RequestContextFilter},
        },
        "handlers": {
            "default": {
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stdout",
                "formatter": "json",
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
            "rq": {"handlers": ["default"], "level": level, "propagate": False},
            "rq.worker": {
                "handlers": ["default"],
                "level": level,
                "propagate": False,
            },
        },
    }
    logging.config.dictConfig(config)
