# Design — 002 Keep tasks in Postgres so they survive restarts, and answer 503 while the database is unreachable

## Decisions

- **Driver: psycopg 3 (`psycopg[binary]>=3.2`), plain parameterised SQL, no ORM.** One table and two statements do not justify SQLAlchemy; the binary wheel bundles libpq, so the slim runtime image needs no apt packages and the Dockerfile stays unchanged. Endpoints stay sync (`def`), as in 001. ADR: Postgres access with psycopg 3 and startup-applied SQL migrations (to be created with `cplat adr add postgres-access-psycopg`).
- **Connection per operation, no pool.** Each store call opens a connection with `connect_timeout=3` and `options="-c statement_timeout=5000"`, and closes it. A refused or timed-out connect raises at once, and after an outage the next request simply connects again, so recovery without a restart (AC-002.5) comes free and there is no stale connection to detect. The cost (a few ms per request in-cluster) is fine for a single-replica task board; a pool is a later optimisation behind the same `TaskStore` interface.
- **Configuration:** the conninfo is `os.environ.get("DATABASE_URL", "")`. An empty conninfo makes libpq read `PGHOST`, `PGPORT`, `PGDATABASE`, `PGUSER`, `PGPASSWORD`, so both injected forms work and nothing is read from a file (spec note). Nothing in the repo holds a connection string.
- **Schema at start, also when the database comes up later.** A small in-repo migration runner (`taskboard13_api/migrations.py`: an ordered tuple of `(version, sql)` plus a `schema_migrations` table, applied in one transaction under `pg_advisory_xact_lock`) runs (a) once in the FastAPI lifespan at start-up, failures logged and swallowed so the process still starts while the database is down, and (b) lazily on the first successful connection of each `TaskStore` instance until it has succeeded once. No manual schema step exists (AC-002.2); re-running is a no-op, so a restart against the same database keeps its data (AC-002.1).
- **Creation order is a stored column** `seq BIGINT GENERATED ALWAYS AS IDENTITY`, and `GET /tasks` orders by it (spec note: never rely on row order) (AC-002.1).
- **`due_date` is a Postgres `DATE`** and is returned with `date.isoformat()`. The 001 validator already enforces the canonical `YYYY-MM-DD` form, so the returned string is byte-identical to the one sent (AC-002.1).
- **`id` stays `uuid.uuid4().hex`**, generated in the app and stored as `TEXT` with a `CHECK (id ~ '^[0-9a-f]{32}$')`.
- **One error type, one handler.** `taskboard13_api.db` turns every `psycopg.OperationalError` (refused connect, connect timeout, `QueryCanceled` from the statement timeout, connection lost mid-call) into `DatabaseUnavailableError`. `main.py` registers one exception handler for it that answers `503 {"error": "The task database is unreachable. Please try again later."}`, and a catch-all handler that answers `500 {"error": "Internal server error."}`. Neither message nor the logs carry the conninfo: the log event `database_unavailable` records only the exception class name and SQLSTATE (AC-002.3, AC-002.4).
- **Validation before database access.** `get_task_store()` only returns a store object and does no I/O, so FastAPI rejects an invalid body with `422` before the endpoint (and the database) is touched, also while the database is down (spec note).
- **`/ready` goes through the store** (`Depends(get_task_store)`, then `store.ping()`): it applies pending migrations if needed, then runs `SELECT 1` with `connect_timeout=2` and `statement_timeout=2000`. A failure raises `DatabaseUnavailableError` and so answers `503` through the same handler. `/health` stays static and never touches the database (AC-002.5).
- **`tasks/api.py` does not change**: the routes already call `store.add` and `store.list`, and errors reach the app-level handler.
- **Test database: a throwaway local Postgres started by the test session** (`initdb` plus `pg_ctl` from the devbox package `postgresql@16`), not testcontainers. That way tests need no Docker daemon, neither on a laptop nor on the CI runner, and `devbox run test` stays the single entry point. See "Test harness".

## Modules

| Module | Responsibility | New / changed |
|---|---|---|
| `src/taskboard13_api/db.py` | `DatabaseUnavailableError`, `database_conninfo()`, `connect()` context manager with the timeouts and error translation | new |
| `src/taskboard13_api/migrations.py` | `MIGRATIONS`, `apply_migrations(conn)` | new |
| `src/taskboard13_api/tasks/store.py` | `TaskStore(conninfo)`: Postgres-backed `add`, `list`, `ensure_schema`, `ping`; `get_task_store()` | rewritten (in-memory store removed) |
| `src/taskboard13_api/tasks/__init__.py` | package docstring ("models and Postgres store") | changed |
| `src/taskboard13_api/main.py` | lifespan (migrate at start), exception handlers (503, 500), `/ready` through the store | changed |
| `pyproject.toml`, `uv.lock` | add `psycopg[binary]>=3.2` | changed |
| `devbox.json` | add package `postgresql@16` (tests only; recipes untouched) | changed |
| `docs/env-vars.md` | `DATABASE_URL`, `PG*` | changed |

Signatures (contract for tests and coders):

```python
# taskboard13_api/db.py
class DatabaseUnavailableError(Exception): ...      # message is safe to log; never contains the conninfo

def database_conninfo() -> str: ...                 # os.environ.get("DATABASE_URL", ""); "" → libpq uses PG* env

@contextmanager
def connect(conninfo: str, *, connect_timeout: int = 3,
            statement_timeout_ms: int = 5000) -> Iterator[psycopg.Connection[tuple[Any, ...]]]: ...
    # psycopg.connect(conninfo, connect_timeout=..., options=f"-c statement_timeout={ms}")
    # commits on clean exit, rolls back on error, always closes;
    # psycopg.OperationalError anywhere inside → raise DatabaseUnavailableError(...) from exc

# taskboard13_api/migrations.py
MIGRATIONS: tuple[tuple[int, str], ...]             # (1, "<create table tasks>")
def apply_migrations(conn: psycopg.Connection[Any]) -> None: ...
    # SELECT pg_advisory_xact_lock(<constant>); CREATE TABLE IF NOT EXISTS schema_migrations(...);
    # run every version not yet in schema_migrations, in order, and record it; same transaction

# taskboard13_api/tasks/store.py
class TaskStore:
    def __init__(self, conninfo: str) -> None: ...  # no I/O
    def ensure_schema(self) -> None: ...            # apply_migrations once per instance (flag + threading.Lock)
    def add(self, title: str, due_date: str | None) -> Task: ...   # uuid4().hex, INSERT, commit
    def list(self) -> list[Task]: ...               # SELECT id, title, due_date FROM tasks ORDER BY seq
    def ping(self) -> None: ...                     # ensure_schema + SELECT 1, 2 s connect / 2 s statement timeout
    # add/list/ping call ensure_schema first; all raise DatabaseUnavailableError when the database is unreachable

def get_task_store() -> TaskStore: ...              # process-wide TaskStore(database_conninfo()), created lazily, cached
```

## Contract

The 001 contract (`POST /tasks`, `GET /tasks`, the `422` body) is unchanged apart from the additions below, and so is the system contract in the spec.

### `GET /tasks`

- `200`: JSON array of `{"id": "<32 lowercase hex>", "title": string, "due_date": "YYYY-MM-DD" | null}`, creation order, oldest first; `[]` when there are none. The values are identical to the `201` responses, also across restarts (AC-002.1, AC-002.2).
- `503`: database unreachable or timing out: `{"error": "The task database is unreachable. Please try again later."}` (AC-002.3).

### `POST /tasks`

- `201`: unchanged (AC-002.2).
- `422`: unchanged FastAPI body. It is checked before any database access, so it answers `422` also while the database is down.
- `503`: database unreachable or timing out. The body is the same as for `GET`, and no task is stored (AC-002.4).

### Probes

- `GET /health`: `200 {"status": "ok"}` always, independent of the database (AC-002.5).
- `GET /ready`: `200 {"status": "ready"}` when pending migrations are applied and `SELECT 1` succeeds within 2 s. Otherwise `503 {"error": "The task database is unreachable. Please try again later."}`. It returns to `200` by itself once the database is reachable again, without a restart (AC-002.5).

### Other errors

- Unexpected exception: `500 {"error": "Internal server error."}`.
- Tests assert only that `error` is a non-empty string, not its exact text.

### Timeouts

- API to database: connect 3 s, statement 5 s; `/ready`: connect 2 s, statement 2 s. No retries inside a request.

## Data

Migration `1`:

```sql
CREATE TABLE tasks (
    id         TEXT PRIMARY KEY CHECK (id ~ '^[0-9a-f]{32}$'),
    seq        BIGINT GENERATED ALWAYS AS IDENTITY UNIQUE,   -- creation order (AC-002.1)
    title      TEXT NOT NULL CHECK (char_length(title) BETWEEN 1 AND 200),
    due_date   DATE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

Bookkeeping: `schema_migrations(version INT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT now())`.

## Test harness (for the testers; written with the acceptance tests)

Put these fixtures in `tests/conftest.py` (the existing `client` fixture stays):

- `pg_server` (session): runs `initdb -D <tempfile.mkdtemp()> -U postgres --auth=trust`, then `pg_ctl -D ... -o "-c listen_addresses=127.0.0.1 -p <free port> -k '' -c fsync=off" -w start`. TCP only: macOS limits socket paths to 104 characters. It exposes `.url` (`postgresql://postgres@127.0.0.1:<port>/postgres`), `.stop()` (`pg_ctl stop -m fast -w`) and `.start()`, and stops the server and removes the directory at teardown. When `initdb` is not on `PATH`, fail with a message pointing to `devbox run test`; never skip.
- `pg_store` (function): drops `tasks` and `schema_migrations` if present, so every test starts on an empty database. It installs `TaskStore(pg_server.url)` via `app.dependency_overrides[get_task_store]`, yields it, and removes the override afterwards.
- Unreachable database: `TaskStore("postgresql://postgres@127.0.0.1:<port bound then closed>/postgres")` installed through the override (AC-002.3, AC-002.4). Use `pg_server.stop()` / `.start()` (always `start()` again in a `finally`) for the "reachable again" halves of AC-002.4 and AC-002.5: the same `TaskStore` object must recover.
- Restart (AC-002.1): create A, B, C through one `TaskStore(pg_server.url)`, then install a **new** `TaskStore(pg_server.url)` (a new process holds a new instance; it re-runs the migrations) and compare `GET /tasks` with the three `201` bodies.
- Empty database (AC-002.2): `pg_store` on a database without tables, then `GET` gives `[]` and `POST {"title": "Buy milk"}` gives `201`, with no schema call made by the test.
- Spec 001 tests (`tests/test_tasks.py`): their `store` fixture becomes `pg_store`, and `TaskStore()` without arguments no longer exists. Delete `test_restart_empties_list`, because AC-001.7 is superseded by AC-002.1.
- Smoke (`tests/test_smoke_tasks.py`): add a read-only `GET /ready` returning `200` at the base URL, which checks that the deployed API reaches its database.
