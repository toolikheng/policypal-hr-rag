"""OllamaProvider against a fake HTTP layer (httpx.MockTransport): no network, no Ollama."""

import json
from collections.abc import Callable

import httpx
import pytest

from policypal.llm.base import LLMError
from policypal.llm.ollama import OllamaProvider
from policypal.llm.prompt import build_messages
from tests.helpers import retrieved_chunk

Handler = Callable[[httpx.Request], httpx.Response]

EXCERPTS = [retrieved_chunk(text="Employees get 16 days of annual leave.")]


def provider(handler: Handler, model: str = "llama3.2:3b") -> OllamaProvider:
    return OllamaProvider(
        base_url="http://ollama:11434",
        model=model,
        timeout_seconds=60,
        transport=httpx.MockTransport(handler),
    )


def chat_reply(content: str) -> httpx.Response:
    return httpx.Response(200, json={"model": "llama3.2:3b", "message": {"content": content}})


def raises(error: Exception) -> Handler:
    def handler(request: httpx.Request) -> httpx.Response:
        raise error

    return handler


def test_generate_sends_the_grounded_prompt_and_returns_the_reply() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return chat_reply("You get 16 days [1].")

    reply = provider(handler).generate("How much annual leave?", EXCERPTS)

    assert reply == "You get 16 days [1]."
    [request] = requests
    assert request.method == "POST"
    assert request.url == "http://ollama:11434/api/chat"
    body = json.loads(request.content)
    assert body["model"] == "llama3.2:3b"
    assert body["messages"] == build_messages("How much annual leave?", EXCERPTS)
    assert body["stream"] is False
    assert body["options"]["temperature"] == 0


def test_generate_uses_the_configured_timeout() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return chat_reply("ok [1]")

    provider(handler).generate("Q?", EXCERPTS)

    assert requests[0].extensions["timeout"]["read"] == 60


@pytest.mark.parametrize(
    ("handler", "reason"),
    [
        (raises(httpx.ConnectError("connection refused")), "llm_unavailable"),
        (raises(httpx.ReadTimeout("timed out")), "llm_timeout"),
        (lambda request: httpx.Response(404, json={"error": "not found"}), "llm_model_missing"),
        (lambda request: httpx.Response(500, json={"error": "out of memory"}), "llm_error"),
        (lambda request: httpx.Response(200, text="not json"), "llm_bad_response"),
        (lambda request: httpx.Response(200, json={"message": {}}), "llm_bad_response"),
        (lambda request: httpx.Response(200, json={"message": {"content": 5}}), "llm_bad_response"),
    ],
    ids=["refused", "timeout", "no-model", "server-error", "not-json", "no-content", "not-text"],
)
def test_ollama_problems_become_an_llm_error_with_a_reason(handler: Handler, reason: str) -> None:
    with pytest.raises(LLMError) as caught:
        provider(handler).generate("Q?", EXCERPTS)

    assert caught.value.reason == reason


def tags(*names: str) -> Handler:
    return lambda request: httpx.Response(200, json={"models": [{"name": n} for n in names]})


def test_status_is_ok_when_the_model_is_downloaded() -> None:
    assert provider(tags("llama3.2:1b", "llama3.2:3b")).status() == "ok"


def test_status_reports_a_missing_model() -> None:
    assert provider(tags("llama3.2:1b")).status() == "model_missing"


def test_model_without_a_tag_means_latest() -> None:
    assert provider(tags("llama3.2:latest"), model="llama3.2").status() == "ok"


@pytest.mark.parametrize(
    "handler",
    [
        raises(httpx.ConnectError("connection refused")),
        raises(httpx.ReadTimeout("timed out")),
        lambda request: httpx.Response(500),
        lambda request: httpx.Response(200, text="not json"),
    ],
    ids=["refused", "timeout", "server-error", "not-json"],
)
def test_status_is_unavailable_when_ollama_cannot_answer(handler: Handler) -> None:
    assert provider(handler).status() == "unavailable"


def test_status_check_uses_a_short_timeout() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"models": []})

    provider(handler).status()

    assert requests[0].url == "http://ollama:11434/api/tags"
    assert requests[0].extensions["timeout"]["read"] == 2
