---
spec_id: 001-create-and-list-tasks-in-memory
title: Create and list tasks (in memory)
status: draft
priority: P1
shape: service-python
---

# 001 — Create and list tasks (in memory)

## Problem

The Task API offers only health and readiness endpoints today, so a client has no way to record a task or see what is on the board. This first feature gives clients the core of the board: create a task with a title and an optional due date, and list all tasks. Tasks are kept in memory, so the API can be tried and built upon before any storage is chosen.

## Stories

As an API client, I want to create a task with a title and, if I have one, a due date, so that the task is on the board.

As an API client, I want to list all tasks, so that I can see everything on the board in the order it was added.

## Acceptance criteria

- **AC-001.1** Given a running service, when a client sends `POST /tasks` with JSON `{"title": "Buy milk", "due_date": "2026-12-01"}`, then the response is `201` with a JSON body holding a non-empty string `id`, `title` `"Buy milk"` and `due_date` `"2026-12-01"`. (smoke)
- **AC-001.2** Given a running service, when a client sends `POST /tasks` with only `{"title": "Call Bob"}`, then the response is `201` and the body's `due_date` is `null`.
- **AC-001.3** Given tasks were created in the order A, B, C, when a client sends `GET /tasks`, then the response is `200` with a JSON array holding A, B and C in that order, each with `id`, `title` and `due_date` exactly as returned when it was created, and every `id` distinct. (smoke)
- **AC-001.4** Given a freshly started service with no tasks created, when a client sends `GET /tasks`, then the response is `200` with an empty JSON array `[]`.
- **AC-001.5** Given a running service, when a client sends `POST /tasks` with the title missing, not a string, empty, whitespace only, or longer than 200 characters, then the response is `422`, the body names the field `title`, and no task is added to the list.
- **AC-001.6** Given a running service, when a client sends `POST /tasks` with a `due_date` that is not a calendar date in the form `YYYY-MM-DD` (for example `"01.12.2026"`, `"2026-02-30"` or `42`), then the response is `422`, the body names the field `due_date`, and no task is added to the list.
- **AC-001.7** Given tasks were created, when the service restarts, then `GET /tasks` returns `200` with `[]`.

## Non-goals

- Persistent storage; tasks survive no restart (AC-001.7).
- Reading, updating, completing or deleting a single task.
- Filtering, sorting options, searching or pagination of the list.
- Authentication, authorisation or per-user task lists.
- Sharing tasks between several running instances of the service.
- Fields beyond title and due date (description, status, priority, time of day, time zone).

## Assumptions

- **A1** Endpoints are `POST /tasks` and `GET /tasks` with JSON bodies and fields `id`, `title`, `due_date` (other option: a versioned prefix such as `/v1/tasks`; affects AC-001.1, AC-001.2, AC-001.3).
- **A2** `id` is an opaque, server-generated string, unique within the running instance (other option: integers counting up from 1; affects AC-001.1, AC-001.3).
- **A3** `due_date` is a plain calendar date `YYYY-MM-DD` without time or time zone; an absent or `null` `due_date` means no due date (other option: a full timestamp; affects AC-001.1, AC-001.2, AC-001.6).
- **A4** Due dates in the past are accepted, so overdue tasks can be recorded (other option: reject with `422`; affects AC-001.6).
- **A5** Title is 1 to 200 characters, must contain a non-whitespace character and is stored exactly as sent (other option: trim surrounding whitespace; other limit; affects AC-001.5).
- **A6** Invalid input answers `422` with the framework's usual validation body naming the offending field (other option: `400` with a custom error shape; affects AC-001.5, AC-001.6).
- **A7** The list is returned in creation order, oldest first, as a bare JSON array (other option: by due date, or wrapped in an object; affects AC-001.3).
- **A8** Unknown extra fields in the create request are ignored (other option: reject with `422`; affects AC-001.1).
- **A9** The endpoints are open like the existing health endpoints, since tasks are in memory and hold no existing data (other option: require a token; see Non-goals).
- **A10** No cap on the number of tasks held in memory (other option: a limit such as 10 000 with an error beyond; affects AC-001.1).

## Open questions

None.

## Changelog

- 2026-11-13 created
