"""Swagger (/docs) must show a request and response example for every endpoint."""

from typing import Any, get_args, get_origin

import pytest
from fastapi.routing import APIRoute
from pydantic import BaseModel

from policypal.api import schemas
from policypal.api.routes import analytics, ask, documents, feedback, health
from policypal.ingest.pipeline import IngestStatus
from tests.helpers import build_test_app

APP = build_test_app("postgresql+psycopg://user:pw@localhost:1/db")
SCHEMA = APP.openapi()
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


def test_the_reingest_status_description_names_every_status() -> None:
    status = SCHEMA["components"]["schemas"]["IngestResultResponse"]["properties"]["status"]
    for value in get_args(IngestStatus):
        assert value in status["description"], value


# Examples are checked where they are written, in Python. Swagger's copy can't be used:
# FastAPI builds /openapi.json with exclude_none=True, which drops every null value from
# the examples (e.g. "model": null in a refusal).
def model_examples(model: type[BaseModel]) -> list[Any]:
    extra = model.model_config.get("json_schema_extra")
    return list(extra.get("examples", [])) if isinstance(extra, dict) else []


def route_examples(route: APIRoute) -> list[tuple[str, type[BaseModel], Any]]:
    """The examples a route declares for its successful replies, with the model to check."""
    found = []
    for status, response in route.responses.items():
        model = response.get("model") or (route.response_model if int(status) < 300 else None)
        media = response.get("content", {}).get("application/json", {})
        if "example" in media:
            examples = [media["example"]]
        else:
            examples = [example["value"] for example in media.get("examples", {}).values()]
        if get_origin(model) is list:  # e.g. list[DocumentSummary]: check each item
            [model] = get_args(model)
            examples = [item for example in examples for item in example]
        if model is not None and issubclass(model, BaseModel):
            found += [(f"{route.path} {status}", model, example) for example in examples]
    return found


# FastAPI keeps included routers nested (privately), so the routes come from each router.
ROUTERS = [analytics.router, ask.router, documents.router, feedback.router, health.router]
ROUTES = [route for router in ROUTERS for route in router.routes if isinstance(route, APIRoute)]
MODELS = [
    model
    for model in vars(schemas).values()
    if isinstance(model, type)
    and issubclass(model, BaseModel)
    and model.__module__ == schemas.__name__
]
EXAMPLES = [
    (model.__name__, model, example) for model in MODELS for example in model_examples(model)
] + [found for route in ROUTES for found in route_examples(route)]


@pytest.mark.parametrize(("where", "model", "example"), EXAMPLES, ids=lambda v: str(v)[:40])
def test_every_example_is_a_valid_body(where: str, model: type[BaseModel], example: Any) -> None:
    # Round trip: every field is allowed and present, and computed fields (status, refused)
    # agree with the rest of the example.
    assert model.model_validate(example).model_dump(mode="json") == example, where


@pytest.mark.parametrize("route", ROUTES, ids=lambda route: route.path)
def test_every_successful_reply_has_a_checked_example(route: APIRoute) -> None:
    model = route.response_model
    model = get_args(model)[0] if get_origin(model) is list else model

    assert route_examples(route) or model_examples(model), route.path


def test_the_checked_routes_are_every_operation() -> None:
    routes = {(method, route.path) for route in ROUTES for method in route.methods}

    assert routes == {(method, path) for method, path, _ in OPERATIONS}
