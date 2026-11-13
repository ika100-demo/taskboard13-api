# Verification — 001 Create and list tasks (in memory)

**Result:** pass
**Commit:** ec09c37 · **Base:** 184473b · **Trace:** 7/7 criteria named by tests (smoke: AC-001.1, AC-001.3)

| Criterion | Verdict | Tests | Implementation | Notes |
|---|---|---|---|---|
| AC-001.1 | met | `tests/test_tasks.py::test_create_with_due_date`; smoke `tests/test_smoke_tasks.py::test_smoke_ac_001_1_create_task` | `src/taskboard13_api/tasks/api.py:15-23`, `src/taskboard13_api/tasks/store.py:18-22`, `src/taskboard13_api/main.py:27` | asserts 201, non-empty string id (also 32 hex), title "Buy milk", due_date "2026-12-01" |
| AC-001.2 | met | `tests/test_tasks.py::test_create_without_due_date` | `src/taskboard13_api/tasks/models.py:17`, `src/taskboard13_api/tasks/api.py:21` | asserts 201 and `due_date is None` |
| AC-001.3 | met | `tests/test_tasks.py::test_list_in_creation_order`; smoke `tests/test_smoke_tasks.py::test_smoke_ac_001_3_list_contains_created` | `src/taskboard13_api/tasks/store.py:18-26`, `src/taskboard13_api/tasks/api.py:26-29` | asserts 200, list equals the three POST bodies in order A, B, C, 3 distinct ids; smoke checks relative order, equality and distinct ids against a shared list |
| AC-001.4 | met | `tests/test_tasks.py::test_list_empty_when_fresh` | `src/taskboard13_api/tasks/store.py:14-16`, `:24-26` | fresh store via `dependency_overrides` (design decision); asserts 200 and `[]` |
| AC-001.5 | met | `tests/test_tasks.py::test_invalid_title_rejected[missing,not-string,null,empty,whitespace,too-long]`, `::test_title_of_200_chars_accepted` | `src/taskboard13_api/tasks/models.py:16`, `:19-24` | all five stated cases; asserts 422, a `detail[].loc` containing `title`, list still `[]`; 200-char boundary accepted |
| AC-001.6 | met | `tests/test_tasks.py::test_invalid_due_date_rejected[01.12.2026,2026-02-30,42,2026-1-1,""]` | `src/taskboard13_api/tasks/models.py:10`, `:17`, `:26-37` | all three spec examples plus two more; asserts 422, `loc` contains `due_date`, list still `[]` |
| AC-001.7 | met | `tests/test_tasks.py::test_restart_empties_list` | `src/taskboard13_api/tasks/store.py:29-33` (module-level in-memory singleton, no persistence) | restart modelled in-process by swapping in a new `TaskStore`, as the design specifies; asserts 200 and `[]` after a task existed |

## Non-goals

No persistence (list in memory only, `store.py:15`), no single-task read/update/complete/delete routes, no filter/sort/search/pagination parameters, no auth, no cross-instance sharing, no fields beyond `id`, `title`, `due_date` (`models.py:40-45`). `main.py` only gains the router import and `include_router`; health, ready, ping, metrics unchanged. ✔

## Deviations from the plan

- t1 merged into t2 (t1's HTTP acceptance tests needed t2's router); recorded in `plan.md`; t2 `done: true`. Acceptable.
- `tests/test_tasks.py` and `tests/test_smoke_tasks.py` are in no task's `files`: they are the frozen acceptance tests from the test phase (unchanged since 3857d38). Acceptable.
- `spec.md`, `design.md`, `plan.md` are spec documents (status change, design, plan). Acceptable.
- `# noqa: B008` on the two `Depends(...)` defaults in `src/taskboard13_api/tasks/api.py:18,27` is production code (the FastAPI dependency idiom, a false positive), not an acceptance-test suppression. Acceptable.

## Contract

Matches `design.md`: `POST /tasks` 201 with `{id, title, due_date}`, id `uuid4().hex`; FastAPI default 422 body with field in `loc`; `GET /tasks` 200 bare array oldest first; strict string title 1–200 with non-blank validator, no trimming; strict string due_date with regex plus `date.fromisoformat`; extra fields ignored (no `extra="forbid"`); structlog `task_created` logs only `task_id`. ✔

## Notes

- The read-only smoke tests `test_smoke_ac_001_1_invalid_title_rejected` and `test_smoke_ac_001_3_list_is_array` name AC-001.1/AC-001.3 but assert less than those criteria (a 422 on empty title; an array). They are the read-only companions for non-dev environments; the writing smoke tests assert the criteria. Both fail without the feature (404), so they are not pass-without-feature smoke findings.

## Mutation check (report only)

12 of 14 mutants of the changed code were caught by the acceptance tests (86 %; spec 152, report only).

Survived (a test that names the criterion would fail if it checked this):
- `src/taskboard13_api/tasks/models.py:30 return value → None`
- `src/taskboard13_api/tasks/store.py:33 return value → None`
