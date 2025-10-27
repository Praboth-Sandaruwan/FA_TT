from __future__ import annotations

import importlib
from collections.abc import Callable
from typing import cast

from fastapi import FastAPI
from fastapi.testclient import TestClient

beginner_main = importlib.import_module("projects.01-beginner.app.main")
create_application = cast(Callable[[], FastAPI], getattr(beginner_main, "create_application"))


def test_health_endpoint_returns_ok() -> None:
    client = TestClient(create_application())
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_root_endpoint_reports_metadata() -> None:
    client = TestClient(create_application())
    response = client.get("/")

    assert response.status_code == 200
    body = response.json()
    assert body["name"]
    assert body["version"]
