"""Postgres access: connection settings and a connection context manager."""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import psycopg


class DatabaseUnavailableError(Exception):
    """The database cannot be reached or a statement failed. The message is safe to log."""


def database_conninfo() -> str:
    """Return DATABASE_URL; empty so libpq falls back to the PG* variables."""
    return os.environ.get("DATABASE_URL", "")


@contextmanager
def connect(
    conninfo: str,
    *,
    connect_timeout: int = 3,
    statement_timeout_ms: int = 5000,
) -> Iterator[psycopg.Connection[tuple[Any, ...]]]:
    """Open a connection; commit on success, roll back on error, always close."""
    try:
        conn = psycopg.connect(
            conninfo,
            connect_timeout=connect_timeout,
            options=f"-c statement_timeout={int(statement_timeout_ms)}",
        )
    except psycopg.OperationalError as exc:
        raise DatabaseUnavailableError("database unavailable: connection failed") from exc
    try:
        try:
            yield conn
            conn.commit()
        except BaseException:
            try:
                conn.rollback()
            except psycopg.Error:
                pass
            raise
    except psycopg.OperationalError as exc:
        raise DatabaseUnavailableError("database unavailable: statement failed") from exc
    finally:
        try:
            conn.close()
        except psycopg.Error:
            pass
