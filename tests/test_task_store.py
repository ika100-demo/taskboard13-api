"""Unit tests for task models and the database access layer."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from taskboard13_api.db import DatabaseUnavailableError, connect, database_conninfo
from taskboard13_api.tasks.models import TaskCreate
from taskboard13_api.tasks.store import get_task_store


def test_singleton() -> None:
    assert get_task_store() is get_task_store()


def test_database_conninfo_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://u@h/db")
    assert database_conninfo() == "postgresql://u@h/db"


def test_database_conninfo_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert database_conninfo() == ""


def test_connect_closed_port_has_no_password() -> None:
    conninfo = "postgresql://user:s3cretpw@127.0.0.1:1/db"  # pragma: allowlist secret
    with pytest.raises(DatabaseUnavailableError) as info:
        with connect(conninfo, connect_timeout=1):
            pass
    assert "s3cretpw" not in str(info.value)


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
