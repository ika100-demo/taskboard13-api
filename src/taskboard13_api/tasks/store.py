"""Postgres-backed task store."""

from __future__ import annotations

import functools
import threading
import uuid
from datetime import date

from taskboard13_api.db import connect, database_conninfo
from taskboard13_api.migrations import apply_migrations
from taskboard13_api.tasks.models import Task


class TaskStore:
    """Keeps tasks in Postgres, in creation order."""

    def __init__(self, conninfo: str) -> None:
        self._conninfo = conninfo
        self._schema_ready = False
        self._schema_lock = threading.Lock()

    def ensure_schema(self) -> None:
        if self._schema_ready:
            return
        with self._schema_lock:
            if self._schema_ready:
                return
            with connect(self._conninfo) as conn:
                apply_migrations(conn)
            self._schema_ready = True

    def add(self, title: str, due_date: str | None) -> Task:
        self.ensure_schema()
        task_id = uuid.uuid4().hex
        due = date.fromisoformat(due_date) if due_date is not None else None
        with connect(self._conninfo) as conn:
            conn.execute(
                "INSERT INTO tasks (id, title, due_date) VALUES (%s, %s, %s)",
                (task_id, title, due),
            )
        return Task(id=task_id, title=title, due_date=due_date)

    def list(self) -> list[Task]:
        self.ensure_schema()
        with connect(self._conninfo) as conn:
            rows = conn.execute("SELECT id, title, due_date FROM tasks ORDER BY seq").fetchall()
        return [
            Task(id=r[0], title=r[1], due_date=r[2].isoformat() if r[2] is not None else None)
            for r in rows
        ]

    def ping(self) -> None:
        self.ensure_schema()
        with connect(self._conninfo, connect_timeout=2, statement_timeout_ms=2000) as conn:
            conn.execute("SELECT 1")


@functools.cache
def get_task_store() -> TaskStore:
    return TaskStore(database_conninfo())
