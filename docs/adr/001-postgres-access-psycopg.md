# ADR-001: Postgres access psycopg

**Status:** Proposed (2026-11-13)

## Context

Spec 002 moves tasks from an in-memory store to Postgres so they survive restarts. The service has a single table and a handful of queries, and the system plan injects `DATABASE_URL`/`PG*` into the container.

## Decision

Postgres via psycopg 3, plain parameterised SQL, in-app migrations applied at start-up under an advisory lock

## Consequences

- No ORM: queries stay explicit and the dependency footprint is one driver.
- The service creates its own schema at start-up; the advisory lock keeps concurrent replicas from racing.
- A schema that outgrows in-app migrations needs a migration tool later (see the migrations agent).
- Every database failure surfaces as one error type, mapped to 503 by the API layer.
