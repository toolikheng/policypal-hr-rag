"""Structured (JSON) logging.

Every log line is one JSON object, so logs can be searched and filtered by field.
Anything passed via `extra=` becomes a field, and the current request ID is added
automatically, e.g.:

    logger.info("request.completed", extra={"status": 200, "latency_ms": 12})
"""

import json
import logging
import sys
from contextvars import ContextVar
from datetime import UTC, datetime

# Set by the request-ID middleware; empty outside a request.
request_id_var: ContextVar[str] = ContextVar("request_id", default="")

# Attributes every LogRecord has. Anything else on a record came from `extra=`.
# uvicorn also adds "color_message", a copy of the message with terminal colour codes.
_NON_EXTRA_ATTRS = set(vars(logging.makeLogRecord({}))) | {"message", "asctime", "color_message"}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        # Fields from `extra=` first, so they can never overwrite the core fields below.
        payload: dict[str, object] = {
            key: value for key, value in vars(record).items() if key not in _NON_EXTRA_ATTRS
        }
        payload |= {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if request_id := request_id_var.get():
            payload["request_id"] = request_id
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(level: str) -> None:
    """Send all log records, including uvicorn's, to stdout as JSON lines.

    Call this once per process, at its entry point. It changes global logging state.
    """
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
    # uvicorn installs its own plain-text handlers at start-up; route its records to ours.
    uvicorn_logger = logging.getLogger("uvicorn")
    uvicorn_logger.handlers = []
    uvicorn_logger.propagate = True
    # No uvicorn access log: the app logs one "request.completed" line per request itself.
    # (uvicorn writes access lines whenever this logger has a handler, even through the root.)
    access_logger = logging.getLogger("uvicorn.access")
    access_logger.handlers = []
    access_logger.propagate = False
