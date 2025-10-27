from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from projects.03-advanced.app.config import get_settings
from projects.03-advanced.app.main import create_app


@pytest.fixture(autouse=True)
def configure_environment(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("ADVANCED_REALTIME_TOKEN", "test-token")
    monkeypatch.setenv("ADVANCED_ALLOWED_ORIGINS", "http://localhost")
    monkeypatch.setenv("ADVANCED_EVENT_TRANSPORT", "memory")
    monkeypatch.setenv("ADVANCED_RATE_LIMIT_DEFAULT", "2/minute")
    monkeypatch.setenv("ADVANCED_TELEMETRY_ENABLED", "true")
    monkeypatch.setenv("ADVANCED_ACTIVITY_STREAM_RATE_LIMIT", "")
    monkeypatch.setenv("ADVANCED_OTEL_EXPORTER_OTLP_ENDPOINT", "")
    get_settings.cache_clear()
    try:
        yield
    finally:
        get_settings.cache_clear()


@pytest.fixture()
def client() -> Iterator[TestClient]:
    app = create_app()
    with TestClient(app) as test_client:
        yield test_client


def test_metrics_endpoint_exposes_prometheus_series(client: TestClient) -> None:
    client.get("/healthz")
    response = client.get("/metrics")
    assert response.status_code == 200
    body = response.text
    assert "advanced_http_requests_total" in body
    assert "advanced_http_request_duration_seconds" in body


def test_rate_limit_returns_429_when_threshold_exceeded(client: TestClient) -> None:
    assert client.get("/").status_code == 200
    assert client.get("/").status_code == 200
    response = client.get("/")
    assert response.status_code == 429
    assert response.json()["detail"] == "Rate limit exceeded"


def test_readiness_probe_reports_pipeline_status(client: TestClient) -> None:
    response = client.get("/readyz")
    payload = response.json()
    assert response.status_code == 200
    assert payload["event_pipeline_ready"] is True
    assert payload["status"] == "ready"
