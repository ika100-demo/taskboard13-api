"""Unit tests for taskboard13_api.db.connect error paths, with a fake psycopg.connect."""

from __future__ import annotations

from typing import Any

import psycopg
import pytest

from taskboard13_api import db
from taskboard13_api.db import DatabaseUnavailableError, connect


class FakeConn:
    def __init__(
        self,
        rollback_error: Exception | None = None,
        close_error: Exception | None = None,
        commit_error: Exception | None = None,
    ) -> None:
        self.rollback_error = rollback_error
        self.close_error = close_error
        self.commit_error = commit_error
        self.calls: list[str] = []

    def commit(self) -> None:
        self.calls.append("commit")
        if self.commit_error:
            raise self.commit_error

    def rollback(self) -> None:
        self.calls.append("rollback")
        if self.rollback_error:
            raise self.rollback_error

    def close(self) -> None:
        self.calls.append("close")
        if self.close_error:
            raise self.close_error


def _patch(monkeypatch: pytest.MonkeyPatch, conn: FakeConn) -> dict[str, Any]:
    seen: dict[str, Any] = {}

    def fake_connect(conninfo: str, **kwargs: Any) -> FakeConn:
        seen["conninfo"] = conninfo
        seen.update(kwargs)
        return conn

    monkeypatch.setattr(db.psycopg, "connect", fake_connect)
    return seen


def test_success_commits_and_closes(monkeypatch: pytest.MonkeyPatch) -> None:
    conn = FakeConn()
    seen = _patch(monkeypatch, conn)
    with connect("x", connect_timeout=2, statement_timeout_ms=100) as c:
        assert c is conn
    assert conn.calls == ["commit", "close"]
    assert seen["connect_timeout"] == 2
    assert seen["options"] == "-c statement_timeout=100"


def test_connect_failure_raises_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*args: Any, **kwargs: Any) -> None:
        raise psycopg.OperationalError("down")

    monkeypatch.setattr(db.psycopg, "connect", boom)
    with pytest.raises(DatabaseUnavailableError, match="connection failed"):
        with connect("x"):
            pytest.fail("body must not run")


def test_operational_error_in_body_rolls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    conn = FakeConn()
    _patch(monkeypatch, conn)
    with pytest.raises(DatabaseUnavailableError) as info:
        with connect("x"):
            raise psycopg.OperationalError("timeout")
    assert str(info.value) == "database unavailable: statement failed"
    assert isinstance(info.value.__cause__, psycopg.OperationalError)
    assert conn.calls == ["rollback", "close"]


def test_operational_error_on_commit(monkeypatch: pytest.MonkeyPatch) -> None:
    conn = FakeConn(commit_error=psycopg.OperationalError("lost"))
    _patch(monkeypatch, conn)
    with pytest.raises(DatabaseUnavailableError, match="statement failed"):
        with connect("x"):
            pass
    assert conn.calls == ["commit", "rollback", "close"]


def test_rollback_error_is_swallowed(monkeypatch: pytest.MonkeyPatch) -> None:
    conn = FakeConn(rollback_error=psycopg.Error("rollback failed"))
    _patch(monkeypatch, conn)
    with pytest.raises(DatabaseUnavailableError, match="statement failed"):
        with connect("x"):
            raise psycopg.OperationalError("timeout")
    assert conn.calls == ["rollback", "close"]


def test_non_operational_error_reraised_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    conn = FakeConn()
    _patch(monkeypatch, conn)
    original = psycopg.IntegrityError("dup")
    with pytest.raises(psycopg.IntegrityError) as info:
        with connect("x"):
            raise original
    assert info.value is original
    assert conn.calls == ["rollback", "close"]


def test_non_psycopg_error_reraised_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    conn = FakeConn(rollback_error=psycopg.Error("nope"))
    _patch(monkeypatch, conn)
    with pytest.raises(ValueError, match="bad"):
        with connect("x"):
            raise ValueError("bad")
    assert conn.calls == ["rollback", "close"]


def test_close_error_is_swallowed(monkeypatch: pytest.MonkeyPatch) -> None:
    conn = FakeConn(close_error=psycopg.Error("close failed"))
    _patch(monkeypatch, conn)
    with connect("x"):
        pass
    assert conn.calls == ["commit", "close"]
