---
spec_id: 001-create-and-list-tasks-in-memory
shape: service-python
spec_hash: 6368d4cc1581
summary: In-memory task store with POST /tasks and GET /tasks
tasks:
- id: t2
  title: Expose POST /tasks and GET /tasks and wire the router into the app
  files: [src/taskboard13_api/tasks/api.py, src/taskboard13_api/main.py, src/taskboard13_api/tasks/__init__.py, src/taskboard13_api/tasks/models.py,
    src/taskboard13_api/tasks/store.py, tests/test_task_store.py]
  covers: [AC-001.1, AC-001.2, AC-001.3, AC-001.4, AC-001.5, AC-001.6, AC-001.7]
  parallel_safe: true
  depends_on: []
---

# Plan — 001 Create and list tasks (in memory)

See [design.md](design.md) for the contract and signatures.

## t2 — Expose POST /tasks and GET /tasks and wire the router into the app

**Files:** src/taskboard13_api/tasks/api.py, src/taskboard13_api/main.py, src/taskboard13_api/tasks/__init__.py, src/taskboard13_api/tasks/models.py, src/taskboard13_api/tasks/store.py, tests/test_task_store.py
**Covers:** AC-001.1, AC-001.2, AC-001.3, AC-001.4, AC-001.5, AC-001.6, AC-001.7
**Goal:** The HTTP layer exactly as in the design contract, using the store through the `get_task_store` dependency so tests can swap in a fresh store.

**Implementation notes:**
- `router = APIRouter(tags=["tasks"])` in `tasks/api.py`.
- `POST /tasks` (sync def, `status_code=201`, `response_model=Task`): body `TaskCreate`, `store: TaskStore = Depends(get_task_store)`, returns `store.add(...)`.
- `GET /tasks` (sync def, `response_model=list[Task]`): returns `store.list()`.
- No custom exception handler: FastAPI's default 422 body names the field in `loc`.
- `main.py`: `from .tasks.api import router as tasks_router`; `app.include_router(tasks_router)` after the middleware setup; health, ready, ping and metrics stay unchanged.
- Emit a structlog `task_created` event with `task_id` (no title, to keep user text out of logs).

**Done when:** all acceptance tests for AC-001.1 to AC-001.7 pass (including the smoke tests for AC-001.1 and AC-001.3 against a local run), the existing tests still pass, and `devbox run ci` is green.

**Merged from t1 — Add task models and in-memory TaskStore** (t1's acceptance tests are HTTP tests that 404 until t2 adds the router; t1's own unit tests and quality are green):

**Files:** src/taskboard13_api/tasks/__init__.py, src/taskboard13_api/tasks/models.py, src/taskboard13_api/tasks/store.py, tests/test_task_store.py
**Covers:** AC-001.3, AC-001.4, AC-001.5, AC-001.6, AC-001.7
**Goal:** The domain layer: request/response models with the validation rules of the spec and a thread-safe, process-local store that keeps tasks in creation order.

**Implementation notes:**
- `tasks/__init__.py`: package docstring only (no re-exports, so t2 does not have to touch it).
- `TaskCreate`: `title: StrictStr` with `min_length=1, max_length=200` and a validator rejecting whitespace-only; never trim.
- `due_date: StrictStr | None = None`; validator requires `^\d{4}-\d{2}-\d{2}$` and a successful `date.fromisoformat`; keep the string as sent. Do not use pydantic `date` (it coerces ints to timestamps).
- Extra fields ignored (pydantic default; do not set `extra="forbid"`).
- `Task(id: str, title: str, due_date: str | None)`.
- `TaskStore` holds a list and a `threading.Lock`; `add` assigns `uuid.uuid4().hex`, appends, returns the `Task`; `list` returns a copy.
- Module-level singleton plus `get_task_store() -> TaskStore` returning it.
- Unit tests in `tests/test_task_store.py`: order, distinct ids, new store is empty, model validation edge cases (200 vs 201 chars, `"   "`, `42`, `"2026-02-30"`, `"01.12.2026"`, `"20261201"`, `null`).

**Done when:** `tests/test_task_store.py` passes and `devbox run quality` is green. The HTTP acceptance tests pass only after t2.

