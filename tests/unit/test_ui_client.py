import json

import httpx
import pytest

from ui.api_client import ApiError, PolicyPalClient, make_client


def client_with(handler) -> PolicyPalClient:
    return PolicyPalClient(
        httpx.Client(transport=httpx.MockTransport(handler), base_url="http://api")
    )


def client_returning(status_code: int, body: dict) -> PolicyPalClient:
    return client_with(lambda request: httpx.Response(status_code, json=body))


def test_health_returns_api_body_when_ok() -> None:
    body = {"status": "ok", "database": "ok", "version": "0.1.0"}

    assert client_returning(200, body).health() == body


def test_health_returns_api_body_when_api_reports_unavailable() -> None:
    body = {"status": "unavailable", "database": "unreachable", "version": "0.1.0"}

    assert client_returning(503, body).health() == body


def test_health_raises_clear_error_when_api_cannot_be_reached() -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    with pytest.raises(ApiError, match="Cannot reach the PolicyPal API"):
        client_with(refuse).health()


def test_health_raises_clear_error_on_unexpected_status() -> None:
    with pytest.raises(ApiError, match="HTTP 500"):
        client_returning(500, {"detail": "Internal Server Error"}).health()


def test_health_raises_clear_error_when_body_is_not_json() -> None:
    not_json = client_with(lambda request: httpx.Response(200, text="<html>proxy page</html>"))

    with pytest.raises(ApiError, match="not valid JSON"):
        not_json.health()


# --- The Phase 3 endpoints -----------------------------------------------------------

ANSWER = {
    "message_id": "6f1c2a9e-3b1d-4c55-9a51-2f0f7d1e8b3a",
    "conversation_id": "0b9e44d1-7c2a-4f6e-8d0b-5a7e3c9f1d24",
    "answer": "Rest days are paid at 2.0 × the hourly rate [1].",
    "mode": "llm",
    "refused": False,
    "citations": [],
    "model": "llama3.2:3b",
    "fallback_reason": None,
    "latency_ms": {"retrieval": 40, "generation": 9000, "total": 9040},
}


def recording(status_code: int, body: object, requests: list[httpx.Request]) -> PolicyPalClient:
    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(status_code, json=body)

    return client_with(handler)


def test_ask_sends_the_question_and_conversation_from_the_ui() -> None:
    requests: list[httpx.Request] = []

    answer = recording(200, ANSWER, requests).ask("Rest day rate?", conversation_id="c-1")

    assert answer == ANSWER
    [request] = requests
    assert (request.method, request.url.path) == ("POST", "/ask")
    assert json.loads(request.content) == {
        "question": "Rest day rate?",
        "conversation_id": "c-1",
        "channel": "ui",
    }


def test_ask_waits_longer_than_the_api_waits_for_the_llm() -> None:
    requests: list[httpx.Request] = []

    recording(200, ANSWER, requests).ask("Q?")

    # The API may wait up to 120 s for Ollama (OLLAMA_TIMEOUT_SECONDS) before falling back.
    assert requests[0].extensions["timeout"]["read"] > 120


def test_feedback_sends_the_vote() -> None:
    requests: list[httpx.Request] = []

    recording(200, {"status": "recorded"}, requests).feedback("m-1", "down", comment="Wrong")

    assert (requests[0].method, requests[0].url.path) == ("POST", "/feedback")
    assert json.loads(requests[0].content) == {
        "message_id": "m-1",
        "rating": "down",
        "comment": "Wrong",
    }


def test_documents_are_listed_and_shown() -> None:
    requests: list[httpx.Request] = []
    rows = [{"id": 3, "slug": "leave-policy"}]

    assert recording(200, rows, requests).list_documents() == rows
    recording(200, {"id": 3}, requests).get_document(3)

    assert [r.url.path for r in requests] == ["/documents", "/documents/3"]


def test_upload_sends_the_file_token_and_replace_flag() -> None:
    requests: list[httpx.Request] = []
    body = {"status": "created", "document": {"slug": "x"}}

    result = recording(201, body, requests).upload("x.md", b"# X", token="t0k", replace=True)

    assert result == body
    [request] = requests
    assert (request.method, request.url.path) == ("POST", "/documents")
    assert request.url.params["replace"] == "true"
    assert request.headers["X-Admin-Token"] == "t0k"
    assert b'filename="x.md"' in request.content and b"# X" in request.content


def test_reingest_returns_the_results() -> None:
    requests: list[httpx.Request] = []
    results = [{"slug": "leave-policy", "status": "unchanged", "chunks": 20}]

    assert recording(200, {"results": results}, requests).reingest(token="t0k") == results
    assert requests[0].headers["X-Admin-Token"] == "t0k"


def test_api_error_carries_the_apis_message_status_and_conflict() -> None:
    body = {"detail": "A policy named 'x' already exists ...", "conflict": "name_taken"}

    with pytest.raises(ApiError) as caught:
        client_returning(409, body).upload("x.md", b"# X", token="t")

    assert str(caught.value) == "A policy named 'x' already exists ..."
    assert caught.value.status_code == 409
    assert caught.value.conflict == "name_taken"


def test_validation_errors_are_turned_into_one_readable_message() -> None:
    body = {"detail": [{"loc": ["body", "question"], "msg": "String should have at least 3"}]}

    with pytest.raises(ApiError, match="question: String should have at least 3"):
        client_returning(422, body).ask("hi")


def test_a_timeout_is_a_clear_error() -> None:
    def slow(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out")

    with pytest.raises(ApiError, match="took too long"):
        client_with(slow).ask("Q?")


def test_make_client_points_at_api_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("API_URL", "http://api.example:9000")

    assert str(make_client().base_url) == "http://api.example:9000"


def test_a_server_error_shows_the_request_id_to_report() -> None:
    body = {"detail": "Internal server error.", "request_id": "abc123"}

    with pytest.raises(ApiError, match=r"HTTP 500, reference abc123"):
        client_returning(500, body).ask("Q?")


def test_an_error_page_that_is_not_json_still_reports_its_status() -> None:
    # For example a proxy's HTML page when the API container is down.
    proxy_page = client_with(lambda request: httpx.Response(502, text="<html>Bad gateway</html>"))

    with pytest.raises(ApiError, match=r"HTTP 502") as caught:
        proxy_page.ask("Q?")

    assert caught.value.status_code == 502
