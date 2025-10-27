from __future__ import annotations

import asyncio
import json
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from projects.03-advanced.app.config import get_settings
from projects.03-advanced.app.main import create_app
from projects.03-advanced.app.realtime import broker

REALTIME_TOKEN = "test-token"


@pytest.fixture(autouse=True)
def configure_environment(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("ADVANCED_REALTIME_TOKEN", REALTIME_TOKEN)
    monkeypatch.setenv("ADVANCED_ALLOWED_ORIGINS", "http://localhost")
    monkeypatch.setenv("ADVANCED_WEBSOCKET_MAX_CONNECTIONS", "10")
    monkeypatch.setenv("ADVANCED_EVENT_TRANSPORT", "memory")
    monkeypatch.setenv("ADVANCED_RATE_LIMIT_DEFAULT", "1000/minute")
    monkeypatch.setenv("ADVANCED_ACTIVITY_STREAM_RATE_LIMIT", "")
    monkeypatch.setenv("ADVANCED_TELEMETRY_ENABLED", "false")
    get_settings.cache_clear()
    asyncio.run(broker.reset())
    try:
        yield
    finally:
        asyncio.run(broker.reset())
        get_settings.cache_clear()


@pytest.fixture()
def client() -> Iterator[TestClient]:
    app = create_app()
    with TestClient(app) as test_client:
        yield test_client


def test_websocket_requires_token(client: TestClient) -> None:
    with pytest.raises(WebSocketDisconnect) as exc:
        client.websocket_connect("/ws/boards/demo")
    assert exc.value.code == 4401


def test_websocket_accepts_bearer_token(client: TestClient) -> None:
    payload = {
        "action": "chat.message",
        "user": "casey",
        "message": "Hello team",
        "payload": {"message": "Hello team"},
    }
    with client.websocket_connect(
        "/ws/boards/demo",
        headers={"Authorization": f"Bearer {REALTIME_TOKEN}"},
    ) as websocket:
        websocket.send_json(payload)
        event = websocket.receive_json()
    assert event["action"] == "chat.message"
    assert event["payload"]["message"] == "Hello team"
    assert event["active_connections"] == 1


def test_broadcast_reaches_multiple_clients(client: TestClient) -> None:
    message = {
        "action": "card.added",
        "user": "alex",
        "payload": {"title": "Write websocket tests", "column": "backlog"},
    }
    with client.websocket_connect(f"/ws/boards/demo?token={REALTIME_TOKEN}") as first:
        with client.websocket_connect(f"/ws/boards/demo?token={REALTIME_TOKEN}") as second:
            first.send_json(message)
            first_event = first.receive_json()
            second_event = second.receive_json()

    assert first_event["payload"]["title"] == "Write websocket tests"
    assert second_event["payload"]["title"] == "Write websocket tests"
    assert first_event["active_connections"] == 2
    assert second_event["active_connections"] == 2


def test_sse_requires_token(client: TestClient) -> None:
    response = client.get("/sse/activity")
    assert response.status_code == 401


def test_sse_activity_stream_receives_board_events(client: TestClient) -> None:
    stream = client.stream("GET", f"/sse/activity?token={REALTIME_TOKEN}")
    response = stream.__enter__()
    try:
        assert response.status_code == 200
        line_iter = response.iter_lines()

        with client.websocket_connect(f"/ws/boards/demo?token={REALTIME_TOKEN}") as websocket:
            websocket.send_json(
                {
                    "action": "card.added",
                    "user": "pat",
                    "payload": {"title": "Synchronise SSE", "column": "in_progress"},
                }
            )
            websocket.receive_json()

        data_line: str | None = None
        for _ in range(20):
            try:
                line = next(line_iter)
            except StopIteration:  # pragma: no cover - defensive guard
                break
            if line == "":
                if data_line:
                    break
                continue
            if line.startswith("event: heartbeat"):
                data_line = None
                continue
            if line.startswith("data: "):
                data_line = line
                break

        assert data_line is not None, "Expected SSE data line but none was received"
        payload = json.loads(data_line.removeprefix("data: ").strip())
        assert payload["action"] == "card.added"
        assert payload["payload"]["title"] == "Synchronise SSE"
    finally:
        stream.__exit__(None, None, None)


def test_security_headers_are_applied(client: TestClient) -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert response.headers["Content-Security-Policy"].startswith("default-src 'self'")
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["X-Content-Type-Options"].lower() == "nosniff"
    assert response.headers["Strict-Transport-Security"].startswith("max-age=")
    assert "server" not in {key.lower() for key in response.headers.keys()}


def test_cors_configuration_is_strict(client: TestClient) -> None:
    response = client.options(
        "/",
        headers={
            "Origin": "http://localhost",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "Authorization",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost"
    allowed_methods = {
        method.strip()
        for method in response.headers["access-control-allow-methods"].split(",")
    }
    assert allowed_methods == {"GET", "HEAD", "OPTIONS"}
    allowed_headers = {
        header.strip()
        for header in response.headers["access-control-allow-headers"].split(",")
    }
    assert "Authorization" in allowed_headers
    disallowed_origin = client.options(
        "/",
        headers={
            "Origin": "https://malicious.invalid",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert "access-control-allow-origin" not in {
        key.lower() for key in disallowed_origin.headers.keys()
    }
