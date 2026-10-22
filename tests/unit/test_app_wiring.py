"""How the app is put together: startup checks, the LLM choice and unexpected errors."""

import json

import pytest
from fastapi.testclient import TestClient

from policypal.llm import build_llm
from policypal.llm.ollama import OllamaProvider
from policypal.logging_setup import JsonFormatter
from tests.fakes import FakeEmbedder
from tests.helpers import build_test_app, make_settings

# Nothing listens on port 1; these tests never touch the database.
NO_DATABASE = "postgresql+psycopg://user:pw@localhost:1/db"


def test_ollama_provider_is_built_from_settings() -> None:
    settings = make_settings(
        NO_DATABASE,
        ollama_base_url="http://ollama:11434",
        ollama_model="llama3.2:1b",
        ollama_timeout_seconds=30,
    )

    llm = build_llm(settings)

    assert isinstance(llm, OllamaProvider)
    assert llm.model == "llama3.2:1b"


def test_extractive_mode_has_no_llm() -> None:
    assert build_llm(make_settings(NO_DATABASE, llm_provider="extractive")) is None


def test_app_refuses_to_start_if_the_embedding_size_does_not_match_the_database() -> None:
    app = build_test_app(NO_DATABASE, embedder=FakeEmbedder("other-model", dimension=768))

    with pytest.raises(ValueError, match="768-number vectors.*384-number vectors"):
        with TestClient(app):
            pass


def test_unexpected_error_is_a_500_with_the_request_id(caplog: pytest.LogCaptureFixture) -> None:
    app = build_test_app(NO_DATABASE)

    @app.get("/boom")
    def boom() -> None:
        raise RuntimeError("secret internal detail")

    # Format records as the app's JSON at the moment they are logged.
    caplog.handler.setFormatter(JsonFormatter())
    with TestClient(app) as client:
        response = client.get("/boom", headers={"X-Request-ID": "trace-500"})

    assert response.status_code == 500
    assert response.headers["X-Request-ID"] == "trace-500"
    assert response.json() == {"detail": "Internal server error.", "request_id": "trace-500"}
    assert "secret internal detail" not in response.text
    [failure] = [
        json.loads(line)
        for line in caplog.text.splitlines()
        if json.loads(line)["message"] == "request.failed"
    ]
    assert failure["request_id"] == "trace-500"
    assert failure["level"] == "ERROR"
    assert "secret internal detail" in failure["exception"]
