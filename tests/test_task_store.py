"""Unit tests for task models and the in-memory store."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from taskboard13_api.tasks.models import TaskCreate
from taskboard13_api.tasks.store import TaskStore, get_task_store


def test_new_store_is_empty() -> None:
    assert TaskStore().list() == []


def test_order_and_distinct_ids() -> None:
    store = TaskStore()
    for title in ("A", "B", "C"):
        store.add(title, None)
    tasks = store.list()
    assert [t.title for t in tasks] == ["A", "B", "C"]
    assert len({t.id for t in tasks}) == 3


def test_list_returns_copy() -> None:
    store = TaskStore()
    store.add("A", None)
    store.list().clear()
    assert len(store.list()) == 1


def test_singleton() -> None:
    assert get_task_store() is get_task_store()


def test_title_length_limits() -> None:
    assert TaskCreate(title="a" * 200).title == "a" * 200
    with pytest.raises(ValidationError):
        TaskCreate(title="a" * 201)


@pytest.mark.parametrize("title", ["", "   ", 42, None])
def test_invalid_titles(title: object) -> None:
    with pytest.raises(ValidationError):
        TaskCreate(title=title)  # type: ignore[arg-type]


def test_title_not_trimmed() -> None:
    assert TaskCreate(title=" a ").title == " a "


@pytest.mark.parametrize("due", [42, "2026-02-30", "01.12.2026", "20261201"])
def test_invalid_due_dates(due: object) -> None:
    with pytest.raises(ValidationError):
        TaskCreate(title="x", due_date=due)  # type: ignore[arg-type]


def test_valid_and_null_due_dates() -> None:
    assert TaskCreate(title="x", due_date="2026-12-01").due_date == "2026-12-01"
    assert TaskCreate(title="x", due_date=None).due_date is None
    assert TaskCreate(title="x").due_date is None
