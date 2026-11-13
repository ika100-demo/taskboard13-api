---
spec_id: 002-keep-tasks-in-postgres-so-they-survive
shape: service-python
spec_hash: 545b8e97adb3
summary: Postgres-backed TaskStore (psycopg 3, startup migrations) with 503 on database outage and a database-aware /ready
tasks:
  - id: t1
    title: Postgres access layer, migrations and Postgres-backed TaskStore
    files: [pyproject.toml, uv.lock, devbox.json, src/taskboard13_api/db.py, src/taskboard13_api/migrations.py, src/taskboard13_api/tasks/store.py, src/taskboard13_api/tasks/__init__.py, tests/test_task_store.py, docs/env-vars.md]
    covers: [AC-002.1, AC-002.2, AC-002.4]
    parallel_safe: true
    depends_on: []
    done: true
  - id: t2
    title: 503 and 500 error handlers, migrate at start-up, database-aware /ready
    files: [src/taskboard13_api/main.py, tests/test_health.py]
    covers: [AC-002.3, AC-002.4, AC-002.5]
    parallel_safe: true
    depends_on: [t1]
    done: true
---

# Plan — 002 Keep tasks in Postgres so they survive restarts, and answer 503 while the database is unreachable

See [design.md](design.md) for the contract, signatures, schema and the test harness the acceptance tests use.

## t1 — Postgres access layer, migrations and Postgres-backed TaskStore

**Files:** pyproject.toml, uv.lock, devbox.json, src/taskboard13_api/db.py, src/taskboard13_api/migrations.py, src/taskboard13_api/tasks/store.py, src/taskboard13_api/tasks/__init__.py, tests/test_task_store.py, docs/env-vars.md
**Covers:** AC-002.1, AC-002.2, AC-002.4
**Goal:** Tasks are stored in Postgres in creation order. The schema is created by the service itself, and every database failure surfaces as `DatabaseUnavailableError` with nothing stored.

**Implementation notes:**
- Add `psycopg[binary]>=3.2` to `[project].dependencies` and regenerate `uv.lock`: the Dockerfile builds with `uv sync --locked`. Add `postgresql@16` to devbox `packages` so the test harness finds `initdb` and `pg_ctl`, and leave the recipes untouched.
- `db.py`: `DatabaseUnavailableError`, `database_conninfo()` (`DATABASE_URL`, empty string as the fallback so libpq reads `PG*`), and a `connect()` context manager with `connect_timeout` and `options="-c statement_timeout=<ms>"`. It commits on success, rolls back on error and always closes. It wraps `psycopg.OperationalError` raised by connect or by any statement, and the message carries no conninfo.
- `migrations.py`: `MIGRATIONS = ((1, <CREATE TABLE tasks ...>),)` exactly as in the design's Data section. `apply_migrations(conn)` takes `pg_advisory_xact_lock(<fixed bigint>)`, creates `schema_migrations` if missing and applies the missing versions in order, all in one transaction.
- `tasks/store.py`: `TaskStore(conninfo)` per the design signatures. `ensure_schema()` runs once per instance (a flag plus `threading.Lock`; the flag is set only after success, so a failed attempt is retried on the next call). `add`, `list` and `ping` call it first. `add` inserts `uuid.uuid4().hex`, title and due date (pass `date.fromisoformat(due_date)` or `None`). `list` runs `ORDER BY seq` and maps `due_date` back with `.isoformat()`. `ping` uses `connect_timeout=2`, `statement_timeout_ms=2000` and `SELECT 1`.
- `get_task_store()`: a lazily created, cached `TaskStore(database_conninfo())` (`functools.cache`). Construction does no I/O, so validation still answers `422` while the database is down.
- Parameterised SQL only (bandit, and no injection risk); `mypy --strict` clean.
- `tasks/__init__.py`: the docstring says "models and Postgres store".
- `tests/test_task_store.py`: keep the model validation tests and remove the in-memory store tests (`TaskStore()` without arguments no longer exists). Add unit tests for `database_conninfo()` (`DATABASE_URL` set or unset, via `monkeypatch`), and a test that `connect()` against a closed local port raises `DatabaseUnavailableError` whose message holds no password.
- `docs/env-vars.md`: a "Database" section with `DATABASE_URL` (no default; injected by the system's `postgres` resource) and `PGHOST`/`PGPORT`/`PGDATABASE`/`PGUSER`/`PGPASSWORD` (used when `DATABASE_URL` is unset), plus the fixed timeouts.

**Done when:** the acceptance tests for AC-002.1 and AC-002.2 pass, and so do the spec 001 tests (as the testers moved them onto `pg_store`). The test for AC-002.4 passes its "nothing stored" half, but its `503` assertion passes only after t2. `tests/test_task_store.py` passes and `devbox run quality` is green.

## t2 — 503 and 500 error handlers, migrate at start-up, database-aware /ready

**Files:** src/taskboard13_api/main.py, tests/test_health.py
**Covers:** AC-002.3, AC-002.4, AC-002.5
**Goal:** A database outage answers `503 {"error": ...}` on `/tasks` and `/ready` while `/health` stays `200`. The service migrates its schema at start-up without crashing when the database is down, and it recovers by itself.

**Implementation notes:**
- `app.add_exception_handler(DatabaseUnavailableError, ...)`: return `JSONResponse(503, {"error": "The task database is unreachable. Please try again later."})` and log a `database_unavailable` warning with the exception class and SQLSTATE only.
- A catch-all `Exception` handler: return `JSONResponse(500, {"error": "Internal server error."})` and log `unhandled_error` via structlog with the exception type.
- Add a `lifespan` that calls `get_task_store().ensure_schema()`, catches `DatabaseUnavailableError`, logs `database_schema_deferred` and starts anyway. Pass it with `FastAPI(..., lifespan=lifespan)`.
- `/ready`: `def ready(store: TaskStore = Depends(get_task_store))` calls `store.ping()` and returns `{"status": "ready"}`. A failure reaches the 503 handler. `/health`, `/ping` and `/metrics` stay unchanged.
- `tests/test_health.py`: `test_ready_returns_ready` overrides `get_task_store` with a stub whose `ping()` returns. Add a unit test where the stub's `ping()` raises `DatabaseUnavailableError` and the response is `503` with a non-empty `error`. `/health` gets no override and still returns `200`.

**Done when:** the acceptance tests for AC-002.3, AC-002.4 and AC-002.5 pass, along with all other tests (the smoke tests too, against a local run with a database). `devbox run ci` is green.
