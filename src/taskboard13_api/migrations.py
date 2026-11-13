"""Schema migrations applied by the service itself."""

from __future__ import annotations

from typing import Any

import psycopg

_LOCK_KEY = 7_002_001_002

MIGRATIONS: tuple[tuple[int, str], ...] = (
    (
        1,
        """
CREATE TABLE tasks (
    id         TEXT PRIMARY KEY CHECK (id ~ '^[0-9a-f]{32}$'),
    seq        BIGINT GENERATED ALWAYS AS IDENTITY UNIQUE,
    title      TEXT NOT NULL CHECK (char_length(title) BETWEEN 1 AND 200),
    due_date   DATE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
)
""",
    ),
)


def apply_migrations(conn: psycopg.Connection[Any]) -> None:
    """Apply missing migrations in order, in one transaction (caller commits)."""
    conn.execute("SELECT pg_advisory_xact_lock(%s)", (_LOCK_KEY,))
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations ("
        "version INT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT now())"
    )
    rows = conn.execute("SELECT version FROM schema_migrations").fetchall()
    applied = {row[0] for row in rows}
    for version, sql in MIGRATIONS:
        if version in applied:
            continue
        conn.execute(sql)
        conn.execute("INSERT INTO schema_migrations (version) VALUES (%s)", (version,))
