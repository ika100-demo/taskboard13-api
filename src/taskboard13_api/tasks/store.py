"""Thread-safe, process-local in-memory task store."""

from __future__ import annotations

import threading
import uuid

from taskboard13_api.tasks.models import Task


class TaskStore:
    """Keeps tasks in creation order."""

    def __init__(self) -> None:
        self._tasks: list[Task] = []
        self._lock = threading.Lock()

    def add(self, title: str, due_date: str | None) -> Task:
        task = Task(id=uuid.uuid4().hex, title=title, due_date=due_date)
        with self._lock:
            self._tasks.append(task)
        return task

    def list(self) -> list[Task]:
        with self._lock:
            return list(self._tasks)


_store = TaskStore()


def get_task_store() -> TaskStore:
    return _store
