"""FastAPI application factory.

Run with:  uvicorn policypal.api.main:create_app --factory
"""

import logging
import re
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response

from policypal import __version__
from policypal.api.routes import health
from policypal.config import Settings, get_settings
from policypal.db import make_engine
from policypal.logging_setup import configure_logging, request_id_var

logger = logging.getLogger("policypal.api")

# Accept a caller's request ID only if it is short and safe to echo back and log.
_VALID_REQUEST_ID = re.compile(r"^[A-Za-z0-9-]{1,64}$")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
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
    app.include_router(health.router)
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
        response = await call_next(request)
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
