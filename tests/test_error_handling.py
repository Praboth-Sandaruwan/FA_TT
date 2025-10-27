from __future__ import annotations

import logging

import pytest
from fastapi import status
from httpx import AsyncClient
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError

from projects.01-beginner.app.core.logging import RequestContextFilter
from projects.01-beginner.app.errors import ApplicationError
from projects.01-beginner.app.main import create_app

pytestmark = pytest.mark.asyncio


@pytest.fixture()
def app():
    return create_app()


async def test_application_error_response_schema(app) -> None:
    @app.get("/error/application")
    async def trigger_application_error() -> None:  # pragma: no cover - defined in test
        raise ApplicationError(
            "Example failure",
            code="example_error",
            status_code=status.HTTP_418_IM_A_TEAPOT,
            details={"foo": "bar"},
        )

    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/error/application")

    assert response.status_code == status.HTTP_418_IM_A_TEAPOT
    payload = response.json()
    request_id = response.headers["X-Request-ID"]
    assert payload == {
        "code": "example_error",
        "message": "Example failure",
        "details": {"foo": "bar", "request_id": request_id},
    }


async def test_validation_error_response_schema(app) -> None:
    class ExamplePayload(BaseModel):
        name: str

    @app.post("/error/validation")
    async def create_item(_: ExamplePayload) -> None:  # pragma: no cover - defined in test
        return None

    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post("/error/validation", json={})

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    payload = response.json()
    request_id = response.headers["X-Request-ID"]
    assert payload["code"] == "validation_error"
    assert payload["message"] == "Request validation failed."
    assert "errors" in payload["details"]
    assert payload["details"]["request_id"] == request_id


async def test_not_found_error_response_schema(app) -> None:
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/error/not-found")

    assert response.status_code == status.HTTP_404_NOT_FOUND
    payload = response.json()
    request_id = response.headers["X-Request-ID"]
    assert payload["code"] == "not_found"
    assert payload["message"]
    assert payload["details"]["request_id"] == request_id


async def test_integrity_error_response_schema(app) -> None:
    @app.get("/error/database")
    async def trigger_integrity_error() -> None:  # pragma: no cover - defined in test
        raise IntegrityError("statement", {}, Exception("constraint"))

    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/error/database")

    assert response.status_code == status.HTTP_409_CONFLICT
    payload = response.json()
    request_id = response.headers["X-Request-ID"]
    assert payload["code"] == "db_integrity_error"
    assert payload["message"] == "Database integrity violation."
    assert payload["details"]["request_id"] == request_id


async def test_unhandled_error_hides_internal_details(app) -> None:
    @app.get("/error/unhandled")
    async def trigger_unhandled_error() -> None:  # pragma: no cover - defined in test
        raise RuntimeError("Sensitive detail")

    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/error/unhandled")

    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    payload = response.json()
    request_id = response.headers["X-Request-ID"]
    assert payload == {
        "code": "server_error",
        "message": "Internal server error.",
        "details": {"request_id": request_id},
    }
    assert "Sensitive" not in response.text


class _InMemoryHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__(level=logging.INFO)
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


async def test_request_id_attached_to_logs(app) -> None:
    logger = logging.getLogger("tests.error_handling")
    handler = _InMemoryHandler()
    handler.addFilter(RequestContextFilter())
    logger.addHandler(handler)
    original_level = logger.level
    logger.setLevel(logging.INFO)

    @app.get("/log")
    async def emit_log() -> dict[str, str]:  # pragma: no cover - defined in test
        logger.info("Log entry")
        return {"status": "ok"}

    try:
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.get("/log")
    finally:
        logger.removeHandler(handler)
        logger.setLevel(original_level)
        handler.close()

    request_id = response.headers["X-Request-ID"]
    matching = [record for record in handler.records if record.getMessage() == "Log entry"]
    assert matching
    assert getattr(matching[0], "request_id", None) == request_id
