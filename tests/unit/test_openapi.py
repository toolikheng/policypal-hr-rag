"""Swagger (/docs) must show a request and response example for every endpoint."""

from typing import Any

import pytest

from tests.helpers import build_test_app

SCHEMA = build_test_app("postgresql+psycopg://user:pw@localhost:1/db").openapi()
OPERATIONS = [
    (method.upper(), path, operation)
    for path, methods in SCHEMA["paths"].items()
    for method, operation in methods.items()
]


def has_example(media: dict[str, Any]) -> bool:
    if "example" in media or "examples" in media:
        return True
    ref = media.get("schema", {}).get("$ref", "")
    component = SCHEMA["components"]["schemas"].get(ref.rsplit("/", 1)[-1], {})
    return "examples" in component


@pytest.mark.parametrize(("method", "path", "operation"), OPERATIONS, ids=lambda v: str(v))
def test_every_request_body_has_an_example(
    method: str, path: str, operation: dict[str, Any]
) -> None:
    for media_type, media in operation.get("requestBody", {}).get("content", {}).items():
        if media_type == "multipart/form-data":
            # A file upload: Swagger shows a file picker, so each field is described instead.
            ref = media["schema"]["$ref"].rsplit("/", 1)[-1]
            fields = SCHEMA["components"]["schemas"][ref]["properties"]
            assert all("description" in field for field in fields.values()), f"{method} {path}"
        else:
            assert has_example(media), f"{method} {path}: request body has no example"


@pytest.mark.parametrize(("method", "path", "operation"), OPERATIONS, ids=lambda v: str(v))
def test_every_response_has_an_example(method: str, path: str, operation: dict[str, Any]) -> None:
    for status, response in operation["responses"].items():
        for media in response.get("content", {}).values():
            assert has_example(media), f"{method} {path}: response {status} has no example"


def test_ask_is_documented() -> None:
    ask = SCHEMA["paths"]["/ask"]["post"]

    assert {"200", "422", "503"} <= set(ask["responses"])
    examples = ask["responses"]["200"]["content"]["application/json"]["examples"]
    assert {"answered", "extractive", "refused"} <= set(examples)


def test_admin_token_is_documented_as_an_api_key() -> None:
    schemes = SCHEMA["components"]["securitySchemes"]

    assert schemes["APIKeyHeader"] == {
        "type": "apiKey",
        "in": "header",
        "name": "X-Admin-Token",
        "description": "The admin token (ADMIN_TOKEN in .env).",
    }
    for path in ("/documents", "/documents/reingest"):
        assert SCHEMA["paths"][path]["post"]["security"] == [{"APIKeyHeader": []}]
