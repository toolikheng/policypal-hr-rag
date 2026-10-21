import json
import logging

from policypal.logging_setup import JsonFormatter, request_id_var


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
