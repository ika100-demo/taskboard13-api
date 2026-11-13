# Verification — 002 Keep tasks in Postgres so they survive restarts, and answer 503 while the database is unreachable

**Result:** pass
**Commit:** ef14a55 · **Base:** 23e4dba · **Trace:** 5/5 criteria named by tests (AC-002.1..AC-002.5 -> `tests/test_persistence.py`; AC-002.5 also -> `tests/test_smoke_tasks.py`)

Test run (Phase 3): `devbox run ci` green, 51 passed / 7 skipped (the skips are smoke tests without `SMOKE_BASE_URL`; the Postgres harness fails rather than skips when `initdb` is missing, `tests/conftest.py:84-85`). Acceptance tests are unchanged since the red commit: `git diff 228aecf..HEAD -- tests/` touches only `test_db_unit.py`, `test_health.py` and `test_task_store.py`, none of which name an AC-002 criterion.

| Criterion | Verdict | Tests | Implementation | Notes |
|---|---|---|---|---|
| AC-002.1 | met | `tests/test_persistence.py::test_restart_keeps_tasks_in_order` | `src/taskboard13_api/tasks/store.py:44-51` (`ORDER BY seq`, `isoformat()`), `src/taskboard13_api/migrations.py:15-21` (`seq` identity column), `src/taskboard13_api/tasks/store.py:33-42` | Creates A, B, C (two dated, one `null`), installs a new `TaskStore` on the same database (restart per design's harness), asserts `200` and that the list equals the three `201` bodies (id, title, due_date) in order. |
| AC-002.2 | met | `tests/test_persistence.py::test_empty_database_needs_no_schema_step` | `src/taskboard13_api/tasks/store.py:23-31,59-61`, `src/taskboard13_api/db.py:17-19`, `src/taskboard13_api/migrations.py:27-40`, `src/taskboard13_api/main.py:37-48` | Drops the tables, goes through `DATABASE_URL` and the real cached `get_task_store()` (no override), asserts `GET` `200 []`, then `POST {"title": "Buy milk"}` `201`. No schema call by the test. |
| AC-002.3 | met | `tests/test_persistence.py::test_get_tasks_503_when_db_unreachable` | `src/taskboard13_api/db.py:30-37`, `src/taskboard13_api/main.py:58-70` | Store on a refused port; asserts `503` and `error` is a non-empty `str`. |
| AC-002.4 | met | `tests/test_persistence.py::test_post_503_and_nothing_stored` | `src/taskboard13_api/db.py:30-49`, `src/taskboard13_api/main.py:58-70`, `src/taskboard13_api/tasks/store.py:33-42` | Stops the real server, asserts `503` with non-empty `error`, restarts it, asserts `GET /tasks` `200` without the task. The 503 body carries no id, so absence is checked by title on an emptied database, which is the strongest check available. |
| AC-002.5 | met | `tests/test_persistence.py::test_ready_503_while_down_health_200_then_recovers`, `tests/test_persistence.py::test_ready_503_when_db_unreachable`, `tests/test_smoke_tasks.py::test_smoke_ac_002_5_ready_reaches_database` | `src/taskboard13_api/main.py:89-93` (`/ready` -> `store.ping()`), `src/taskboard13_api/tasks/store.py:53-56` (2 s / 2 s `SELECT 1`), `src/taskboard13_api/main.py:83-86` (`/health` static) | `/ready` `200`, then `503` while stopped with `/health` `200`, then `200` again on the same store object with no restart. Connection per operation (no pool) gives the recovery. |

## Non-goals

The spec lists no non-goals. No auth, no web code, no change to `tasks/api.py` or the 001 validation contract. No template-owned files (Dockerfile, CI workflow, `.claude/settings.json`) changed. ✔

## Deviations from the plan

Both tasks are `done: true`. Files changed outside every task's `files`:

- `tests/conftest.py`, `tests/test_persistence.py`, `tests/test_tasks.py`, `tests/test_smoke_tasks.py`: the acceptance tests and harness from the tester commits, exactly as the design's "Test harness" section specifies (`test_restart_empties_list` deleted because AC-001.7 is superseded). Acceptable.
- `tests/test_db_unit.py`: unit tests for the `db.connect` error paths (rollback, commit failure, close failure, re-raise of non-operational errors). No criterion ids, internals only. Acceptable.
- `devbox.lock`: lock for the `postgresql@16` package added to `devbox.json` (t1). Acceptable.
- `docs/adr/001-postgres-access-psycopg.md`, `docs/adr/README.md`: the ADR the design calls for. Acceptable.
- `docs/specs/001-create-and-list-tasks-in-memory/spec.md`: AC-001.7 struck through as superseded by AC-002.1, with a changelog line. This matches AC-002.1's "(replaces AC-001.7)". Acceptable.
- `docs/backlog.md`: the generated `cplat spec index` table. It still shows 002 as `approved`, but it is regenerated on build/ship. Acceptable.

## Contract

Matches `design.md`. The `503` body is `{"error": "The task database is unreachable. Please try again later."}` (`main.py:67-70`). The catch-all is `500 {"error": "Internal server error."}` (`main.py:73-76`). Logs carry only the exception class and SQLSTATE (`main.py:31-34,62-66`), and the error messages never include the conninfo (`db.py:37,49`; the test is `tests/test_task_store.py::test_connect_closed_port_has_no_password`). The timeouts are 3 s / 5 s by default and 2 s / 2 s for `/ready` (`db.py:26-27`, `store.py:55`). The migrations run under `pg_advisory_xact_lock` in one transaction (`migrations.py:29-40`). `get_task_store()` does no I/O, so `422` still comes before database access. One note: the start-up `lifespan` migration (`main.py:37-48`) is not exercised by any test, because `TestClient` is not used as a context manager. AC-002.2 is proven through the lazy `ensure_schema` path, which the design allows as an equal route.

## Unresolved test-review findings

| Test | Criterion | Finding |
|---|---|---|
| `tests/test_health.py::test_ready_returns_ready` | AC-002.5 | Owned by plan task t2, which rewrites it. **Resolved in build:** it now overrides `get_task_store` with a stub whose `ping()` returns, and `test_ready_returns_503_when_database_down` was added (`tests/test_health.py:15-49`). |
| `tests/test_task_store.py::TaskStore()` no-arg tests | AC-002.1 | Owned by plan task t1, which rewrites it. **Resolved in build:** the in-memory store tests were removed, and tests for `database_conninfo()` and the closed-port `connect()` were added (`tests/test_task_store.py:15-32`). |

## Mutation check (report only)

12 of 20 mutants of the changed code were caught by the acceptance tests (60 %; spec 152, report only).

Survived (a test that names the criterion would fail if it checked this):
- `src/taskboard13_api/db.py:26 3 → 4`
- `src/taskboard13_api/db.py:27 5000 → 5001`
- `src/taskboard13_api/main.py:34 return value → None`
- `src/taskboard13_api/main.py:76 return value → None`
- `src/taskboard13_api/main.py:76 500 → 501`
- `src/taskboard13_api/migrations.py:9 7002001002 → 7002001003`
- `src/taskboard13_api/tasks/store.py:31 True → False`
- `src/taskboard13_api/tasks/store.py:55 2 → 3`
