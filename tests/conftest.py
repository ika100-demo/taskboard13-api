"""Shared pytest fixtures."""

from __future__ import annotations

import shutil
import socket
import subprocess  # nosec B404
import tempfile
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from taskboard13_api.main import app


@pytest.fixture()
def client() -> TestClient:
    """A TestClient for the FastAPI application."""
    return TestClient(app)


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port: int = sock.getsockname()[1]
    return port


class PgServer:
    """A throwaway local Postgres reachable over TCP."""

    def __init__(self, data_dir: Path, port: int) -> None:
        self.data_dir = data_dir
        self.port = port
        self.url = f"postgresql://postgres@127.0.0.1:{port}/postgres"

    def start(self) -> None:
        options = f"-c listen_addresses=127.0.0.1 -p {self.port} -k '' -c fsync=off"
        subprocess.run(  # nosec B603 B607
            [
                "pg_ctl",
                "-D",
                str(self.data_dir),
                "-l",
                str(self.data_dir.parent / "server.log"),
                "-o",
                options,
                "-w",
                "start",
            ],
            check=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def stop(self) -> None:
        subprocess.run(  # nosec B603 B607
            ["pg_ctl", "-D", str(self.data_dir), "-m", "fast", "-w", "stop"],
            check=True,
            capture_output=True,
        )

    def reset(self) -> None:
        """Drop the application tables so a test starts on an empty database."""
        subprocess.run(  # nosec B603 B607
            [
                "psql",
                self.url,
                "-q",
                "-c",
                "DROP TABLE IF EXISTS tasks, schema_migrations",
            ],
            check=True,
            capture_output=True,
        )


@pytest.fixture(scope="session")
def pg_server() -> Iterator[PgServer]:
    """A Postgres server for the whole test session (initdb + pg_ctl)."""
    if shutil.which("initdb") is None or shutil.which("pg_ctl") is None:
        pytest.fail("initdb/pg_ctl not on PATH: run the tests with `devbox run test`")
    data_dir = Path(tempfile.mkdtemp(prefix="tb13-pg-"))
    server = PgServer(data_dir / "data", _free_port())
    subprocess.run(  # nosec B603 B607
        ["initdb", "-D", str(server.data_dir), "-U", "postgres", "--auth=trust"],
        check=True,
        capture_output=True,
    )
    server.start()
    try:
        yield server
    finally:
        try:
            server.stop()
        except subprocess.CalledProcessError:
            pass  # already stopped by a test
        shutil.rmtree(data_dir, ignore_errors=True)


@pytest.fixture()
def pg_store(pg_server: PgServer) -> Iterator[object]:
    """A TaskStore on an empty database, installed through the dependency override."""
    from taskboard13_api.tasks.store import TaskStore, get_task_store

    pg_server.reset()
    store = TaskStore(pg_server.url)
    app.dependency_overrides[get_task_store] = lambda: store
    try:
        yield store
    finally:
        app.dependency_overrides.pop(get_task_store, None)


@pytest.fixture()
def install_store(pg_server: PgServer) -> Iterator[Callable[[str], object]]:
    """Install a new TaskStore(conninfo) as the app's store; cleaned up afterwards."""
    from taskboard13_api.tasks.store import TaskStore, get_task_store

    def _install(conninfo: str) -> object:
        store = TaskStore(conninfo)
        app.dependency_overrides[get_task_store] = lambda: store
        return store

    try:
        yield _install
    finally:
        app.dependency_overrides.pop(get_task_store, None)


@pytest.fixture()
def unreachable_url() -> str:
    """A conninfo whose port was bound and then closed: connections are refused."""
    return f"postgresql://postgres@127.0.0.1:{_free_port()}/postgres"
