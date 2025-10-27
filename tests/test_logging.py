from __future__ import annotations

import io
import json
import logging

from projects.02-intermediate.app.core.config import Settings
from projects.02-intermediate.app.core.context import bind_request_id, reset_request_id
from projects.02-intermediate.app.core.logging import configure_logging


def test_configure_logging_outputs_json_with_request_id() -> None:
    settings = Settings(environment="test")
    settings.log_level = "INFO"
    configure_logging(settings)

    root_logger = logging.getLogger()
    handler = next(
        (h for h in root_logger.handlers if isinstance(h, logging.StreamHandler)),
        None,
    )
    assert handler is not None, "Expected JSON stream handler to be configured"

    buffer = io.StringIO()
    previous_stream = handler.setStream(buffer)

    token = bind_request_id("req-json-1")
    try:
        logger = logging.getLogger("projects.02-intermediate.tests.logging")
        logger.info("structured log event", extra={"component": "unit-test"})
    finally:
        handler.flush()
        reset_request_id(token)
        handler.setStream(previous_stream)

    log_lines = buffer.getvalue().strip().splitlines()
    assert log_lines, "Expected structured log line to be captured"
    payload = json.loads(log_lines[-1])

    assert payload["message"] == "structured log event"
    assert payload["request_id"] == "req-json-1"
    assert payload["environment"] == settings.environment
    assert payload["level"] == "INFO"
    assert payload["component"] == "unit-test"
    assert payload["service"] == settings.project_name
