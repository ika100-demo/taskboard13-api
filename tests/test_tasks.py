"""Acceptance tests for spec 001: create and list tasks (backed by Postgres since spec 002)."""

from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from taskboard13_api.main import app


def _names_field(response, field: str) -> bool:
    detail = response.json()["detail"]
    return any(field in entry["loc"] for entry in detail)


def test_create_with_due_date(pg_store):  # AC-001.1
    payload = {"title": "Buy milk", "due_date": "2026-12-01"}
    response = TestClient(app).post("/tasks", json=payload)
    assert response.status_code == 201
    body = response.json()
    assert isinstance(body["id"], str) and body["id"]
    assert re.fullmatch(r"[0-9a-f]{32}", body["id"])
    assert body["title"] == "Buy milk"
    assert body["due_date"] == "2026-12-01"


def test_create_without_due_date(client, pg_store):  # AC-001.2
    response = client.post("/tasks", json={"title": "Call Bob"})
    assert response.status_code == 201
    assert response.json()["due_date"] is None


def test_list_in_creation_order(client, pg_store):  # AC-001.3
    created = [
        client.post("/tasks", json={"title": "A", "due_date": "2026-01-01"}).json(),
        client.post("/tasks", json={"title": "B"}).json(),
        client.post("/tasks", json={"title": "C", "due_date": "2026-03-03"}).json(),
    ]
    response = client.get("/tasks")
    assert response.status_code == 200
    assert response.json() == created
    assert [t["title"] for t in created] == ["A", "B", "C"]
    assert len({t["id"] for t in created}) == 3


def test_list_empty_when_fresh(client, pg_store):  # AC-001.4
    response = client.get("/tasks")
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"title": 5},
        {"title": None},
        {"title": ""},
        {"title": "   "},
        {"title": "x" * 201},
    ],
    ids=["missing", "not-string", "null", "empty", "whitespace", "too-long"],
)
def test_invalid_title_rejected(client, pg_store, body):  # AC-001.5
    response = client.post("/tasks", json=body)
    assert response.status_code == 422
    assert _names_field(response, "title")
    assert client.get("/tasks").json() == []


def test_title_of_200_chars_accepted(client, pg_store):  # AC-001.5
    assert client.post("/tasks", json={"title": "x" * 200}).status_code == 201


@pytest.mark.parametrize("due", ["01.12.2026", "2026-02-30", 42, "2026-1-1", ""])
def test_invalid_due_date_rejected(client, pg_store, due):  # AC-001.6
    response = client.post("/tasks", json={"title": "Ok", "due_date": due})
    assert response.status_code == 422
    assert _names_field(response, "due_date")
    assert client.get("/tasks").json() == []
