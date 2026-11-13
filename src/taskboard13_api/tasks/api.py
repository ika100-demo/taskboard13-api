"""HTTP routes for tasks."""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends

from taskboard13_api.tasks.models import Task, TaskCreate
from taskboard13_api.tasks.store import TaskStore, get_task_store

router = APIRouter(tags=["tasks"])
log = structlog.get_logger(__name__)


@router.post("/tasks", status_code=201, response_model=Task)
def create_task(
    body: TaskCreate,
    store: TaskStore = Depends(get_task_store),  # noqa: B008
) -> Task:
    """Create a task."""
    task = store.add(body.title, body.due_date)
    log.info("task_created", task_id=task.id)
    return task


@router.get("/tasks", response_model=list[Task])
def list_tasks(store: TaskStore = Depends(get_task_store)) -> list[Task]:  # noqa: B008
    """List tasks, oldest first."""
    return store.list()
