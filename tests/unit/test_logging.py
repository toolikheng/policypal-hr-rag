import json
import logging

from policypal.logging_setup import JsonFormatter, configure_logging, request_id_var


def make_record(message: str, **extra: object) -> logging.LogRecord:
    record = logging.LogRecord("policypal.test", logging.INFO, __file__, 1, message, None, None)
    for key, value in extra.items():
        setattr(record, key, value)
    return record


def test_log_line_is_json_with_level_logger_and_message() -> None:
    line = JsonFormatter().format(make_record("request.completed"))

    payload = json.loads(line)
    assert payload["level"] == "INFO"
    assert payload["logger"] == "policypal.test"
    assert payload["message"] == "request.completed"
    assert "timestamp" in payload


def test_extra_fields_become_json_fields() -> None:
    line = JsonFormatter().format(make_record("request.completed", status=200, latency_ms=12))

    payload = json.loads(line)
    assert payload["status"] == 200
    assert payload["latency_ms"] == 12


def test_current_request_id_is_included() -> None:
    token = request_id_var.set("abc123")
    try:
        payload = json.loads(JsonFormatter().format(make_record("hello")))
    finally:
        request_id_var.reset(token)

    assert payload["request_id"] == "abc123"


def test_configure_logging_sends_uvicorn_logs_through_the_json_handler() -> None:
    root, uvicorn_logger = logging.getLogger(), logging.getLogger("uvicorn")
    saved_root = (list(root.handlers), root.level)
    saved_uvicorn = (list(uvicorn_logger.handlers), uvicorn_logger.propagate)
    # Simulate uvicorn's own start-up logging config: a plain-text handler, no propagation.
    uvicorn_logger.handlers = [logging.StreamHandler()]
    uvicorn_logger.propagate = False
    try:
        configure_logging("INFO")

        assert uvicorn_logger.handlers == []
        assert uvicorn_logger.propagate is True
        [handler] = root.handlers
        assert isinstance(handler.formatter, JsonFormatter)
    finally:
        root.handlers, root.level = saved_root
        uvicorn_logger.handlers, uvicorn_logger.propagate = saved_uvicorn


def test_uvicorn_terminal_colour_copy_of_the_message_is_dropped() -> None:
    record = make_record("Started server process [1]", color_message="\x1b[36m%d\x1b[0m")

    payload = json.loads(JsonFormatter().format(record))

    assert "color_message" not in payload


def test_extra_fields_cannot_overwrite_core_fields() -> None:
    record = make_record("real message", level="FAKE", logger="fake.logger", timestamp="never")

    payload = json.loads(JsonFormatter().format(record))

    assert (payload["level"], payload["logger"]) == ("INFO", "policypal.test")
    assert payload["timestamp"] != "never"


def test_configure_logging_keeps_uvicorns_access_log_off() -> None:
    # The app logs one "request.completed" line per request; uvicorn's own access line
    # would log every request twice. uvicorn writes access lines only when the
    # "uvicorn.access" logger has a handler (its own, or the root's through propagation).
    root, access = logging.getLogger(), logging.getLogger("uvicorn.access")
    saved_root = (list(root.handlers), root.level)
    saved_access = (list(access.handlers), access.propagate)
    access.handlers, access.propagate = [], False  # what `--no-access-log` sets up
    try:
        configure_logging("INFO")

        assert not access.hasHandlers()
    finally:
        root.handlers, root.level = saved_root
        access.handlers, access.propagate = saved_access
