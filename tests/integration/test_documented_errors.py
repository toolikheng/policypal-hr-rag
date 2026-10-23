"""Every error example in Swagger (/docs) is exactly what the API really returns."""

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from policypal.ingest.pipeline import SAMPLE_POLICIES_DIR, ingest_file
from tests.fakes import FakeEmbedder
from tests.helpers import build_test_app
from tests.sample_data import UPLOAD_DEMO_POLICY

TOKEN = "test-admin-token"
ADMIN = {"X-Admin-Token": TOKEN}


@pytest.fixture
def client(migrated_database_url: str, engine: Engine, tmp_path: Path) -> Iterator[TestClient]:
    # The default MAX_UPLOAD_MB (5), as in the documented example.
    app = build_test_app(migrated_database_url, admin_token=TOKEN, upload_dir=tmp_path / "up")
    with TestClient(app) as client:
        yield client


def documented(client: TestClient, method: str, path: str, status: int) -> list[Any]:
    """The example bodies Swagger shows for this response."""
    schema = client.get("/openapi.json").json()
    content = schema["paths"][path][method]["responses"][str(status)]["content"]
    media = content["application/json"]
    if "example" in media:
        return [media["example"]]
    return [example["value"] for example in media["examples"].values()]


def assert_documented(client: TestClient, method: str, path: str, response: httpx.Response) -> None:
    examples = documented(client, method, path, response.status_code)
    assert response.json() in examples, (
        f"{method.upper()} {path} {response.status_code}: the API returned\n"
        f"{json.dumps(response.json())}\nbut Swagger shows\n{json.dumps(examples)}"
    )


def upload(client: TestClient, filename: str, data: bytes, **kwargs: Any) -> httpx.Response:
    headers = kwargs.pop("headers", ADMIN)
    files = {"file": (filename, data, "application/octet-stream")}
    return client.post("/documents", files=files, headers=headers, params=kwargs)


def test_document_errors(client: TestClient) -> None:
    assert_documented(client, "get", "/documents/{document_id}", client.get("/documents/999999"))
    response = client.get("/documents/leave-policy")
    assert_documented(client, "get", "/documents/{document_id}", response)


def test_ask_validation_error(client: TestClient) -> None:
    assert_documented(client, "post", "/ask", client.post("/ask", json={"question": "hi"}))


@pytest.mark.parametrize("path", ["/documents", "/documents/reingest"])
def test_admin_token_errors(client: TestClient, path: str) -> None:
    for headers in ({}, {"X-Admin-Token": "guess"}):
        response = client.post(path, headers=headers)
        assert_documented(client, "post", path, response)


def test_admin_disabled_error(migrated_database_url: str, engine: Engine) -> None:
    with TestClient(build_test_app(migrated_database_url)) as client:
        response = client.post("/documents/reingest", headers=ADMIN)
        assert_documented(client, "post", "/documents/reingest", response)


def test_upload_errors(client: TestClient, engine: Engine) -> None:
    ingest_file(engine, FakeEmbedder(), SAMPLE_POLICIES_DIR / "leave-policy.md", "sample")
    demo = UPLOAD_DEMO_POLICY.read_bytes()
    upload(client, "leave-guide.md", demo)

    responses = [
        upload(client, "leave-guide.md", demo + b"\nEdited.\n"),  # 409, uploaded policy
        upload(client, "leave-policy.md", demo),  # 409, sample policy
        upload(client, "big.md", b"#" * (5 * 1024 * 1024 + 1)),  # 413
        upload(client, "notes.txt", b"# Notes"),  # 415
        upload(client, "fake.pdf", b"# Not a PDF"),  # 422
    ]

    assert [r.status_code for r in responses] == [409, 409, 413, 415, 422]
    for response in responses:
        assert_documented(client, "post", "/documents", response)


def test_database_unavailable_error() -> None:
    app = build_test_app("postgresql+psycopg://nobody:nothing@localhost:1/none")
    with TestClient(app) as client:
        assert_documented(client, "get", "/documents", client.get("/documents"))
        response = client.post("/ask", json={"question": "Annual leave?"})
        assert_documented(client, "post", "/ask", response)
        response = client.post(
            "/feedback", json={"message_id": "6f1c2a9e-3b1d-4c55-9a51-2f0f7d1e8b3a", "rating": "up"}
        )
        assert_documented(client, "post", "/feedback", response)


def test_feedback_validation_error(client: TestClient) -> None:
    payload = {"message_id": "6f1c2a9e-3b1d-4c55-9a51-2f0f7d1e8b3a", "rating": "meh"}
    assert_documented(client, "post", "/feedback", client.post("/feedback", json=payload))


def test_feedback_unknown_message_error(client: TestClient) -> None:
    payload = {"message_id": "6f1c2a9e-3b1d-4c55-9a51-2f0f7d1e8b3a", "rating": "up"}
    assert_documented(client, "post", "/feedback", client.post("/feedback", json=payload))
