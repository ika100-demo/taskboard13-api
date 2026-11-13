"""Acceptance tests for spec 002: tasks kept in Postgres, 503 while it is unreachable."""

from __future__ import annotations

from fastapi.testclient import TestClient

from taskboard13_api.main import app


def _error_is_non_empty_string(response) -> bool:
    error = response.json()["error"]
    return isinstance(error, str) and error != ""


def test_restart_keeps_tasks_in_order(pg_server, pg_store, install_store):  # AC-002.1
    client = TestClient(app)
    created = [
        client.post("/tasks", json={"title": "A", "due_date": "2026-01-01"}),
        client.post("/tasks", json={"title": "B", "due_date": None}),
        client.post("/tasks", json={"title": "C", "due_date": "2026-03-03"}),
    ]
    assert [r.status_code for r in created] == [201, 201, 201]
    bodies = [r.json() for r in created]

    install_store(pg_server.url)  # a new instance, as after a restart
    response = client.get("/tasks")

    assert response.status_code == 200
    assert response.json() == bodies
    assert [t["title"] for t in response.json()] == ["A", "B", "C"]


def test_empty_database_needs_no_schema_step(client, pg_server, monkeypatch):  # AC-002.2
    from taskboard13_api.tasks.store import get_task_store

    pg_server.reset()
    # Configuration path: DATABASE_URL, no dependency override, fresh cached store.
    app.dependency_overrides.pop(get_task_store, None)
    monkeypatch.setenv("DATABASE_URL", pg_server.url)
    get_task_store.cache_clear()
    try:
        listed = client.get("/tasks")
        assert listed.status_code == 200
        assert listed.json() == []

        created = client.post("/tasks", json={"title": "Buy milk"})
        assert created.status_code == 201
        assert created.json()["title"] == "Buy milk"
        assert client.get("/tasks").json() == [created.json()]
    finally:
        get_task_store.cache_clear()


def test_get_tasks_503_when_db_unreachable(client, install_store, unreachable_url):  # AC-002.3
    install_store(unreachable_url)
    response = client.get("/tasks")
    assert response.status_code == 503
    assert _error_is_non_empty_string(response)


def test_post_503_and_nothing_stored(client, pg_server, pg_store):  # AC-002.4
    assert client.get("/tasks").json() == []  # schema is in place
    pg_server.stop()
    try:
        response = client.post("/tasks", json={"title": "Lost", "due_date": None})
        assert response.status_code == 503
        assert _error_is_non_empty_string(response)
    finally:
        pg_server.start()
    listed = client.get("/tasks")
    assert listed.status_code == 200
    assert "Lost" not in [t["title"] for t in listed.json()]


def test_ready_503_while_down_health_200_then_recovers(client, pg_server, pg_store):  # AC-002.5
    assert client.get("/ready").status_code == 200
    pg_server.stop()
    try:
        assert client.get("/ready").status_code == 503
        assert client.get("/health").status_code == 200
    finally:
        pg_server.start()
    assert client.get("/ready").status_code == 200


def test_ready_503_when_db_unreachable(client, install_store, unreachable_url):  # AC-002.5
    install_store(unreachable_url)
    assert client.get("/ready").status_code == 503
    assert client.get("/health").status_code == 200
