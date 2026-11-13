"""Smoke tests for health/ready/ping endpoints."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from taskboard13_api.db import DatabaseUnavailableError
from taskboard13_api.main import app
from taskboard13_api.tasks.store import get_task_store


class _StubStore:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error

    def ping(self) -> None:
        if self.error is not None:
            raise self.error


@pytest.fixture()
def stub_store() -> Iterator[_StubStore]:
    stub = _StubStore()
    app.dependency_overrides[get_task_store] = lambda: stub
    yield stub
    app.dependency_overrides.pop(get_task_store, None)


def test_health_returns_ok(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ready_returns_ready(client: TestClient, stub_store: _StubStore) -> None:
    response = client.get("/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


def test_ready_returns_503_when_database_down(client: TestClient, stub_store: _StubStore) -> None:
    stub_store.error = DatabaseUnavailableError("database unavailable: connection failed")
    response = client.get("/ready")
    assert response.status_code == 503
    assert response.json()["error"]
    assert client.get("/health").status_code == 200


def test_ping_returns_project_name(client: TestClient) -> None:
    response = client.get("/ping")
    assert response.status_code == 200
    assert response.json() == {"pong": "taskboard13-api"}
