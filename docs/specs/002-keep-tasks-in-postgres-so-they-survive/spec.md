---
spec_id: 002-keep-tasks-in-postgres-so-they-survive
title: Keep tasks in Postgres so they survive restarts, and answer 503 while the database is unreachable
status: approved
priority: P1
shape: service-python
parent: ika100-demo/taskboard13-gitops:001-persistent-tasks-in-postgres-with-a-web
---

# 002 — Keep tasks in Postgres so they survive restarts, and answer 503 while the database is unreachable

## Problem

The taskboard13 Task API keeps tasks in memory, so every restart or redeploy of the API empties the board, and nobody can rely on a task still being there. The only way to see or add tasks is to call the API by hand, because the web component has no features yet. This spec makes the board usable: tasks are kept in a Postgres database that belongs to the system, and people see and create tasks in the web UI.

## System context

Slice of the system plan `001-persistent-tasks-in-postgres-with-a-web` in `ika100-demo/taskboard13-gitops` for `taskboard13-api` (service-python). The system criteria and the contract below are binding: every criterion of this spec implements one of them and names it: `(system AC-<NNN>.<n>)`.

### System criteria

- **AC-001.1** Given tasks A, B and C were created in that order, when the API is restarted or redeployed, then `GET /tasks` returns `200` with A, B and C in that order, each with the same `id`, `title` and `due_date` as when it was created.
- **AC-001.7** Given the database is unreachable, when a client calls `GET /tasks` or `POST /tasks`, then the API answers `503` with a JSON body holding an `error` message and creates no task, and the API's readiness endpoint reports not ready until the database is reachable again.

### Contract

Between `taskboard13-web` (caller, server side only) and `taskboard13-api`. Base URL: env `TASKBOARD13_API_URL` (cluster: `http://taskboard13-api`). No auth (non-goal), no prefix, JSON in and out (`Content-Type: application/json`). The existing contract of the API's spec `001-create-and-list-tasks-in-memory` stays unchanged except for the `503` added below.

### `GET /tasks`

- `200` — JSON array of `{"id": string, "title": string, "due_date": "YYYY-MM-DD" | null}`, creation order, oldest first; `[]` when none. Values identical to the `201` responses, also across API restarts and redeploys.
- `503` — database unreachable: `{"error": "<non-empty message>"}`.

### `POST /tasks`

Request: `{"title": string, "due_date": "YYYY-MM-DD" | null}`; `title` 1 to 200 characters with at least one non-whitespace character, stored as sent; `due_date` absent or `null` means no due date; unknown fields ignored. The web always sends both fields (`due_date: null` when none).

- `201` — the created task `{"id": "<32 lowercase hex>", "title", "due_date"}`; it is in every later `GET /tasks`.
- `422` — validation failed, nothing stored; FastAPI body `{"detail": [{"loc": ["body", "<field>", ...], "msg": "<text>", "type": "...", "input": ...}]}`. Validation runs before any database access, so an invalid body answers `422` even while the database is down. The web maps an entry whose `loc` contains `"title"` to the title field message; a `422` for any other field is treated as an unlisted response.
- `503` — database unreachable: `{"error": "<non-empty message>"}`, nothing stored.

### Probes (API)

- `GET /health` — `200` while the process runs, independent of the database (so Kubernetes does not restart the API during a database outage).
- `GET /ready` — `200` when a database round trip (`SELECT 1`) succeeds, `503` otherwise; it turns `200` again by itself when the database is back.

### Errors

- API errors outside validation use `{"error": "<human-readable message>"}` with status `503` (database unreachable or timing out) or `500` (unexpected); validation errors use the FastAPI `422` body above. Messages never contain connection strings or credentials.
- The web treats every response the contract does not list for that call (any other status, a non-JSON or malformed body, a `422` not naming `title`) like an unreachable API: on load "Tasks could not be loaded. Please try again.", on submit "The task could not be saved. Please try again." with the entered values kept. It never shows an empty list or "No tasks yet" in that case, and never retries a `POST` by itself (no duplicate tasks).

### Timeouts

- Web → API: 5 s total per call (`GET /tasks` and `POST /tasks`), connect included; a timeout or refused connection is handled like an unlisted response (above). No automatic retry; the person retries.
- API → database: connect timeout 3 s and statement timeout 5 s; when either hits, the request answers `503` within about 5 s, so it stays inside the web's 5 s budget in the common case. `/ready`'s check uses a 2 s timeout.
- When the database is down the API keeps running (`/health` 200, `/ready` 503) and reconnects on later requests without a restart; Kubernetes takes the API out of its Service while not ready, so the web then gets a refused or timed-out connection, which it shows as the AC-001.8 messages.

### Provided by the system

The gitops part of this plan wires these for this repo; rely on them, do not ask for them again:

- resource `postgres`: env `DATABASE_URL`, `PGHOST`, `PGPORT`, `PGDATABASE`, `PGUSER`, `PGPASSWORD`

### Notes for this repo

Database settings come from the injected DATABASE_URL (and PG*), never from a file in the repo.
The service creates or migrates its own schema at start; creation order must survive restarts
(store an ordering column, do not rely on row order). id stays 32 lowercase hex chars.
A request body that fails validation still answers 422 even while the database is down.

## Stories

<!-- As a <persona>, I want <goal>, so that <benefit>. -->

## Acceptance criteria

- **AC-002.1** Given tasks A, B and C were created with POST /tasks in that order, when the service restarts against the same database, then GET /tasks returns 200 with A, B and C in that order, each with the same id, title and due_date as in its 201 response (system AC-001.1) (replaces AC-001.7)
- **AC-002.2** Given the service starts with DATABASE_URL pointing at an empty database, when a client sends GET /tasks and then POST /tasks with {"title": "Buy milk"}, then GET answers 200 with [] and POST answers 201, without any manual schema step (system AC-001.1)
- **AC-002.3** Given the database is unreachable, when a client sends GET /tasks, then the response is 503 with a JSON body whose error is a non-empty string (system AC-001.7)
- **AC-002.4** Given the database is unreachable, when a client sends POST /tasks with a valid body, then the response is 503 with a JSON body whose error is a non-empty string, and once the database is reachable again GET /tasks does not contain that task (system AC-001.7)
- **AC-002.5** Given the database is unreachable, when the readiness endpoint GET /ready is called, then it answers 503, while GET /health still answers 200; when the database is reachable again, GET /ready answers 200 without a restart of the service (system AC-001.7)

## Non-goals

## Assumptions

<!-- Spec 149: decisions taken by default, approved with the spec. One bullet each: - **A1** <the decision> (other option: <…>; affects AC-…). A revised one is struck through (~~…~~), never deleted. -->

## Open questions

<!-- Only what may not be decided by default (spec 149): security or access, money, destroying or migrating data, or a request too ambiguous to build. Approval is refused while any is open. Strike answered ones (~~…~~) and fold the answer into the criteria. -->

## Changelog

- 2026-11-13 created from the system plan, with its criteria (spec 147)
- 2026-11-13 approved
