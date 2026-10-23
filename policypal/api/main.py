"""FastAPI application factory.

Run with:  uvicorn policypal.api.main:create_app_from_env --factory
"""

import logging
import re
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy.exc import OperationalError

from policypal import __version__
from policypal.api.errors import database_unavailable, upload_rejected
from policypal.api.routes import analytics, ask, documents, feedback, health
from policypal.config import Settings
from policypal.db import make_engine
from policypal.embeddings import Embedder, build_embedder, check_dimension
from policypal.ingest.uploads import UploadRejected
from policypal.llm import build_llm
from policypal.llm.base import LLMProvider
from policypal.logging_setup import configure_logging, request_id_var

logger = logging.getLogger("policypal.api")

# Accept a caller's request ID only if it is short and safe to echo back and log.
_VALID_REQUEST_ID = re.compile(r"^[A-Za-z0-9-]{1,64}$")


def create_app_from_env() -> FastAPI:
    """Process entry point (used by uvicorn): read settings from the environment and set up
    logging. Process-wide side effects live here, not in create_app()."""
    settings = Settings()
    configure_logging(settings.log_level)
    # /health checks the database's migration on every call, and alembic would log two
    # INFO lines each time. Its warnings and errors still get through.
    logging.getLogger("alembic.runtime.migration").setLevel(logging.WARNING)
    return create_app(settings)


def create_app(
    settings: Settings,
    *,
    embedder: Embedder | None = None,
    llm: LLMProvider | None = None,
) -> FastAPI:
    """Build the API from explicit settings. No global side effects, so tests can build many.

    The embedding model and the LLM client are built from the settings at startup, unless
    they are passed in (tests pass fakes). An app without an LLM answers in extractive mode.
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.settings = settings
        app.state.embedder = embedder if embedder is not None else build_embedder(settings)
        check_dimension(app.state.embedder)  # refuse to start rather than fail on every question
        app.state.llm = llm if llm is not None else build_llm(settings)
        app.state.engine = make_engine(settings.database_url)
        yield
        app.state.engine.dispose()

    app = FastAPI(
        title="PolicyPal API",
        version=__version__,
        description="Answers HR policy questions from fictional sample policies, with citations.",
        lifespan=lifespan,
    )
    app.middleware("http")(request_context)
    app.exception_handler(OperationalError)(database_unavailable)
    app.exception_handler(UploadRejected)(upload_rejected)
    app.include_router(health.router)
    app.include_router(ask.router)
    app.include_router(documents.router)
    app.include_router(feedback.router)
    app.include_router(analytics.router)
    return app


async def request_context(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Give every request an ID (echoed in X-Request-ID) and log one line per request."""
    incoming = request.headers.get("X-Request-ID", "")
    request_id = incoming if _VALID_REQUEST_ID.match(incoming) else uuid.uuid4().hex
    token = request_id_var.set(request_id)
    started = time.perf_counter()
    try:
        try:
            response = await call_next(request)
        except Exception:
            # Logged here, while the request ID is still set. The client gets only the ID,
            # never the error details.
            logger.exception("request.failed", extra={"path": request.url.path})
            response = JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={"detail": "Internal server error.", "request_id": request_id},
            )
        response.headers["X-Request-ID"] = request_id
        logger.info(
            "request.completed",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "latency_ms": round((time.perf_counter() - started) * 1000),
            },
        )
        return response
    finally:
        request_id_var.reset(token)
