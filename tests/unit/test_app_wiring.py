"""How the app is put together: startup checks, the LLM choice and unexpected errors."""

import json

import pytest
from fastapi.testclient import TestClient

from policypal.config import PLACEHOLDER_ADMIN_TOKEN
from policypal.llm import LLMInfo, build_llm, describe_llm
from policypal.llm.ollama import OllamaProvider
from policypal.logging_setup import JsonFormatter
from tests.fakes import FakeEmbedder, FakeLLM
from tests.helpers import ENV_EXAMPLE, NO_DATABASE, build_test_app, make_settings


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


def test_no_llm_is_described_as_extractive_mode() -> None:
    assert describe_llm(None) == LLMInfo(provider="extractive", model=None, status="ok")


def test_an_llm_is_described_by_its_name_model_and_status() -> None:
    llm = FakeLLM(model="llama3.2:3b", status="model_missing")

    assert describe_llm(llm) == LLMInfo(
        provider="fake", model="llama3.2:3b", status="model_missing"
    )


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


def startup_warnings(caplog: pytest.LogCaptureFixture, **settings: object) -> list[dict]:
    caplog.handler.setFormatter(JsonFormatter())
    with TestClient(build_test_app(NO_DATABASE, **settings)):
        pass
    lines = [json.loads(line) for line in caplog.text.splitlines()]
    return [line for line in lines if line["message"] == "admin.placeholder_token"]


def test_the_placeholder_admin_token_is_warned_about_at_startup(
    caplog: pytest.LogCaptureFixture,
) -> None:
    [warning] = startup_warnings(caplog, admin_token=PLACEHOLDER_ADMIN_TOKEN)

    assert warning["level"] == "WARNING"
    assert "ADMIN_TOKEN" in warning["hint"]
    assert PLACEHOLDER_ADMIN_TOKEN not in json.dumps(warning)  # never log a token


@pytest.mark.parametrize("token", ["my-own-long-random-token", None])
def test_no_warning_for_an_own_token_or_admin_switched_off(
    caplog: pytest.LogCaptureFixture, token: str | None
) -> None:
    assert startup_warnings(caplog, admin_token=token) == []


def test_the_placeholder_is_the_token_in_env_example() -> None:
    env_example = ENV_EXAMPLE.read_text(encoding="utf-8")

    assert f"\nADMIN_TOKEN={PLACEHOLDER_ADMIN_TOKEN}\n" in env_example
