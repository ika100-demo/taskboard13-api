"""FastAPI entry point for taskboard13-api."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse, Response
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from pydantic import BaseModel

from . import __version__
from .db import DatabaseUnavailableError
from .logging_config import configure_logging
from .metrics import MetricsMiddleware
from .tasks.api import router as tasks_router
from .tasks.store import TaskStore, get_task_store
from .tracing import configure_tracing, tracing_enabled

configure_logging(level=os.environ.get("LOG_LEVEL", "INFO"))
if tracing_enabled():
    configure_tracing()

logger = structlog.get_logger(__name__)


def _sqlstate(exc: BaseException) -> str | None:
    """SQLSTATE of the underlying database error, if any (never its message)."""
    state = getattr(exc.__cause__, "sqlstate", None)
    return state if isinstance(state, str) else None


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Migrate the schema at start-up; start anyway when the database is down."""
    try:
        get_task_store().ensure_schema()
    except DatabaseUnavailableError as exc:
        logger.warning(
            "database_schema_deferred",
            error_type=type(exc).__name__,
            sqlstate=_sqlstate(exc),
        )
    yield


app = FastAPI(title="taskboard13-api", version=__version__, lifespan=lifespan)
app.add_middleware(MetricsMiddleware)
if tracing_enabled():
    FastAPIInstrumentor.instrument_app(app)
app.include_router(tasks_router)


@app.exception_handler(DatabaseUnavailableError)
async def database_unavailable_handler(
    _request: Request, exc: DatabaseUnavailableError
) -> JSONResponse:
    logger.warning(
        "database_unavailable",
        error_type=type(exc).__name__,
        sqlstate=_sqlstate(exc),
    )
    return JSONResponse(
        status_code=503,
        content={"error": "The task database is unreachable. Please try again later."},
    )


@app.exception_handler(Exception)
async def unhandled_error_handler(_request: Request, exc: Exception) -> JSONResponse:
    logger.error("unhandled_error", error_type=type(exc).__name__)
    return JSONResponse(status_code=500, content={"error": "Internal server error."})


class HealthResponse(BaseModel):
    status: str


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Liveness probe — returns 200 as long as the process is responding."""
    return HealthResponse(status="ok")


@app.get("/ready", response_model=HealthResponse)
def ready(store: TaskStore = Depends(get_task_store)) -> HealthResponse:  # noqa: B008
    """Readiness probe — 200 when the database answers, 503 otherwise."""
    store.ping()
    return HealthResponse(status="ready")


@app.get("/ping")
def ping() -> dict[str, str]:
    """Simple ping endpoint."""
    return {"pong": "taskboard13-api"}


@app.get("/metrics")
def metrics() -> Response:
    """Prometheus scrape endpoint."""
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
