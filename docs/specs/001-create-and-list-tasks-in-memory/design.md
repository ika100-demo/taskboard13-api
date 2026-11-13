# Design — 001 Create and list tasks (in memory)

## Decisions

- Tasks live in a `TaskStore` object (a list guarded by a `threading.Lock`), one per process. Sync FastAPI endpoints run in a thread pool, so the lock keeps appends and the list snapshot consistent; insertion order is creation order (AC-001.3). Nothing is written to disk, so a restart starts empty (AC-001.4, AC-001.7).
- Endpoints get the store through a FastAPI dependency `get_task_store()` (in `taskboard13_api.tasks.store`) that returns the process-wide instance. Tests replace it with `app.dependency_overrides[get_task_store] = lambda: store` where `store = TaskStore()` is a fresh instance; that is how acceptance tests model "freshly started" (AC-001.4) and "restart" (AC-001.7) in-process, and how they check "no task is added" (AC-001.5, AC-001.6). The existing `client` fixture stays unchanged.
- `due_date` is validated as a strict string, not as pydantic `date`: pydantic's lax `date` accepts integers as Unix timestamps (`42` would become `1970-01-01`), and `date.fromisoformat` in Python 3.12 accepts `20261201` too. A field validator therefore requires `^\d{4}-\d{2}-\d{2}$` **and** a successful `date.fromisoformat` (rejects `2026-02-30`); the value is stored and returned as sent (AC-001.6).
- `title` is a strict string (no coercion from numbers), 1–200 characters, must contain a non-whitespace character, stored exactly as sent with no trimming (AC-001.5, A5).
- Validation errors use FastAPI's default `422` body (A6); no custom handler.
- `id` is `uuid.uuid4().hex` (A2).
- No ADR: the in-memory store is feature-local and will be replaced when storage is chosen.
- The single-instance limit (non-goal) means the deployed component must run one replica for the AC-001.3 smoke test to be reliable; this repo does not own replicas (see the report's GITOPS line).

## Modules

| Module | Responsibility | New / changed |
|---|---|---|
| `src/taskboard13_api/tasks/__init__.py` | package marker (docstring only) | new |
| `src/taskboard13_api/tasks/models.py` | `TaskCreate` (request), `Task` (response) pydantic models with validation | new |
| `src/taskboard13_api/tasks/store.py` | `TaskStore`: `add(title, due_date) -> Task`, `list() -> list[Task]`; `get_task_store()` dependency | new |
| `src/taskboard13_api/tasks/api.py` | `router = APIRouter()` with `POST /tasks`, `GET /tasks` | new |
| `src/taskboard13_api/main.py` | `app.include_router(tasks_router)` | changed |

Signatures (contract for tests and coders):

```python
# taskboard13_api/tasks/models.py
class TaskCreate(BaseModel):          # extra fields ignored (pydantic default, A8)
    title: StrictStr                  # Field(min_length=1, max_length=200); validator: must contain non-whitespace
    due_date: StrictStr | None = None # validator: regex ^\d{4}-\d{2}-\d{2}$ and date.fromisoformat succeeds

class Task(BaseModel):
    id: str
    title: str
    due_date: str | None

# taskboard13_api/tasks/store.py
class TaskStore:
    def add(self, title: str, due_date: str | None) -> Task: ...  # assigns uuid4().hex, appends under lock
    def list(self) -> list[Task]: ...                             # copy of the list, creation order

def get_task_store() -> TaskStore: ...  # returns the module-level singleton
```

## Contract

No auth (A9). No prefix (A1). JSON in and out.

### `POST /tasks`

Request body (JSON object):

| Field | Type | Required | Rules |
|---|---|---|---|
| `title` | string | yes | 1–200 characters, at least one non-whitespace character, stored as sent |
| `due_date` | string \| null | no | `YYYY-MM-DD`, a real calendar date; absent or `null` = no due date; past dates accepted (A4) |
| any other field | — | — | ignored (A8) |

Responses:

- `201` — `{"id": "<32 lowercase hex chars>", "title": "<as sent>", "due_date": "<YYYY-MM-DD as sent>" | null}` (AC-001.1, AC-001.2).
- `422` — FastAPI validation body, task not stored (AC-001.5, AC-001.6):

```json
{"detail": [{"type": "<pydantic error type>", "loc": ["body", "title"], "msg": "<text>", "input": "<value>"}]}
```

  Each entry's `loc` starts with `"body"` and contains the offending field name (`"title"` or `"due_date"`); tests assert that some entry's `loc` contains the field, not the exact `type` or `msg`. A body that is not a JSON object also answers `422`.

### `GET /tasks`

- `200` — JSON array of `Task` objects `{"id", "title", "due_date"}`, oldest first, values identical to the `POST` responses; `[]` when none (AC-001.3, AC-001.4, AC-001.7).

## Data

In memory only: a Python list of `Task` inside `TaskStore`; no persistence, no cap (A10).
