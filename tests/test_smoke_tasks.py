"""Smoke tests (spec 001): AC-001.1 and AC-001.3, through the base URL only."""

from __future__ import annotations

import uuid

import httpx
import pytest


@pytest.mark.smoke
@pytest.mark.writes
def test_smoke_ac_001_1_create_task(smoke_base_url: str) -> None:  # AC-001.1
    title = f"smoke-{uuid.uuid4()}"
    response = httpx.post(
        smoke_base_url + "/tasks", json={"title": title, "due_date": "2026-12-01"}, timeout=10
    )
    assert response.status_code == 201
    body = response.json()
    assert isinstance(body["id"], str) and body["id"]
    assert body["title"] == title
    assert body["due_date"] == "2026-12-01"


@pytest.mark.smoke
def test_smoke_ac_001_1_invalid_title_rejected(smoke_base_url: str) -> None:  # AC-001.1 read-only
    response = httpx.post(smoke_base_url + "/tasks", json={"title": ""}, timeout=10)
    assert response.status_code == 422


@pytest.mark.smoke
@pytest.mark.writes
def test_smoke_ac_001_3_list_contains_created(smoke_base_url: str) -> None:  # AC-001.3
    titles = [f"smoke-{uuid.uuid4()}" for _ in range(2)]
    url = smoke_base_url + "/tasks"
    created = [httpx.post(url, json={"title": t}, timeout=10).json() for t in titles]
    response = httpx.get(smoke_base_url + "/tasks", timeout=10)
    assert response.status_code == 200
    listed = response.json()
    ids = [t["id"] for t in listed]
    assert len(set(ids)) == len(ids)
    positions = [ids.index(c["id"]) for c in created]
    assert positions == sorted(positions)
    for c in created:
        assert listed[ids.index(c["id"])] == c


@pytest.mark.smoke
def test_smoke_ac_001_3_list_is_array(smoke_base_url: str) -> None:  # AC-001.3 read-only
    response = httpx.get(smoke_base_url + "/tasks", timeout=10)
    assert response.status_code == 200
    assert isinstance(response.json(), list)
