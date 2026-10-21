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
_STANDARD_RECORD_ATTRS = set(vars(logging.makeLogRecord({}))) | {"message", "asctime"}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if request_id := request_id_var.get():
            payload["request_id"] = request_id
        payload.update(
            {key: value for key, value in vars(record).items() if key not in _STANDARD_RECORD_ATTRS}
        )
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(level: str) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
