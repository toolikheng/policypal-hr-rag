"""POST /ask through the real app and database, with the fake embedder and fake LLM."""

import json
import uuid
from collections.abc import Iterator
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from policypal.answering import EXTRACTIVE_HEADING
from policypal.ingest.pipeline import SAMPLE_POLICIES_DIR, ingest_file
from policypal.llm.base import REFUSAL_SENTENCE, LLMError
from policypal.llm.ollama import OllamaProvider
from tests.fakes import FakeEmbedder, FakeLLM
from tests.helpers import build_test_app

# The fake embedder scores by shared words, so these share many words with the
# Leave Policy's annual leave sections and none with any policy, respectively.
IN_SCOPE = "How many days of annual leave do employees get?"
OUT_OF_SCOPE = "Zebra quantum xylophone?"
# The fake embedder's similarities are lower than the real model's.
TEST_THRESHOLD = 0.3


@pytest.fixture
def leave_policy(engine: Engine) -> None:
    ingest_file(engine, FakeEmbedder(), SAMPLE_POLICIES_DIR / "leave-policy.md", origin="sample")


def ask_client(database_url: str, **kwargs: Any) -> TestClient:
    return TestClient(build_test_app(database_url, min_similarity=TEST_THRESHOLD, **kwargs))


@pytest.fixture
def llm() -> FakeLLM:
    return FakeLLM("Employees get between 14 and 22 days of annual leave [1].", model="tiny:1b")


@pytest.fixture
def client(migrated_database_url: str, leave_policy: None, llm: FakeLLM) -> Iterator[TestClient]:
    with ask_client(migrated_database_url, llm=llm) as client:
        yield client


def ask(client: TestClient, question: str = IN_SCOPE, **fields: Any) -> httpx.Response:
    return client.post("/ask", json={"question": question, **fields})


def test_answer_cites_the_document_and_section(client: TestClient, engine: Engine) -> None:
    response = ask(client)

    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "llm"
    assert body["refused"] is False
    assert body["answer"] == "Employees get between 14 and 22 days of annual leave [1]."
    assert body["model"] == "tiny:1b"
    assert body["fallback_reason"] is None
    [citation] = body["citations"]
    assert citation["number"] == 1
    assert citation["document_title"] == "Leave Policy"
    with engine.connect() as conn:
        stored = conn.execute(
            text("SELECT document_id, section FROM chunks WHERE content = :text"),
            {"text": citation["text"]},
        ).one()
    assert (citation["document_id"], citation["section"]) == tuple(stored)
    assert 0 < citation["similarity"] <= 1


def test_response_has_ids_and_latency(client: TestClient) -> None:
    body = ask(client).json()

    uuid.UUID(body["message_id"])
    uuid.UUID(body["conversation_id"])
    latency = body["latency_ms"]
    assert latency["retrieval"] >= 0
    assert latency["generation"] >= 0
    assert latency["total"] >= latency["retrieval"]


def test_conversation_id_is_kept(client: TestClient) -> None:
    conversation_id = str(uuid.uuid4())

    body = ask(client, conversation_id=conversation_id, channel="ui").json()

    assert body["conversation_id"] == conversation_id


def test_below_threshold_question_gets_the_exact_refusal(client: TestClient, llm: FakeLLM) -> None:
    body = ask(client, OUT_OF_SCOPE).json()

    assert body["answer"] == REFUSAL_SENTENCE == "I couldn't find this in the policies."
    assert body["mode"] == "refused"
    assert body["refused"] is True
    assert body["citations"] == []
    assert body["model"] is None
    assert body["latency_ms"]["generation"] is None
    assert llm.calls == []


def test_extractive_mode_answers_without_an_llm(
    migrated_database_url: str, leave_policy: None
) -> None:
    with ask_client(migrated_database_url, llm_provider="extractive") as client:
        body = ask(client).json()

    assert body["mode"] == "extractive"
    assert body["answer"].startswith(EXTRACTIVE_HEADING)
    assert body["model"] is None
    assert body["fallback_reason"] is None
    assert 1 <= len(body["citations"]) <= 3
    assert all(c["document_title"] == "Leave Policy" for c in body["citations"])


def test_llm_error_falls_back_to_policy_text_with_a_reason(
    migrated_database_url: str, leave_policy: None
) -> None:
    llm = FakeLLM(error=LLMError("llm_timeout", "Ollama did not answer within 60 s."))

    with ask_client(migrated_database_url, llm=llm) as client:
        response = ask(client)

    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "extractive"
    assert body["fallback_reason"] == "llm_timeout"
    assert body["citations"]


def test_ollama_being_down_falls_back_to_policy_text(
    migrated_database_url: str, leave_policy: None
) -> None:
    def refuse_connection(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    ollama = OllamaProvider(
        "http://ollama:11434", "llama3.2:3b", 60, transport=httpx.MockTransport(refuse_connection)
    )

    with ask_client(migrated_database_url, llm=ollama) as client:
        body = ask(client).json()

    assert body["mode"] == "extractive"
    assert body["fallback_reason"] == "llm_unavailable"


def test_llm_answer_without_a_valid_citation_is_replaced(
    migrated_database_url: str, leave_policy: None
) -> None:
    llm = FakeLLM("You get plenty of leave, trust me.")

    with ask_client(migrated_database_url, llm=llm) as client:
        body = ask(client).json()

    assert body["mode"] == "extractive"
    assert body["fallback_reason"] == "llm_no_valid_citation"
    assert "trust me" not in body["answer"]


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"question": ""},
        {"question": "   hi   "},
        {"question": "x" * 1001},
        {"question": 42},
        {"question": IN_SCOPE, "channel": "email"},
        {"question": IN_SCOPE, "conversation_id": "not-a-uuid"},
    ],
    ids=["missing", "empty", "too-short", "too-long", "not-text", "bad-channel", "bad-id"],
)
def test_invalid_input_is_a_422(client: TestClient, payload: dict[str, Any]) -> None:
    response = client.post("/ask", json=payload)

    assert response.status_code == 422
    assert response.json()["detail"]


def test_question_is_trimmed_before_its_length_is_checked(client: TestClient, llm: FakeLLM) -> None:
    ask(client, f"   {IN_SCOPE}   ")

    assert llm.calls[0][0] == IN_SCOPE


def test_question_text_is_not_logged(client: TestClient, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level("INFO")

    ask(client, "Annual leave days for Siti binti Ahmad?")

    [record] = [r for r in caplog.records if r.getMessage() == "ask.answered"]
    assert record.mode == "llm"
    assert "Siti" not in caplog.text
    assert "Siti" not in json.dumps(vars(record), default=str)


def test_database_down_is_a_503() -> None:
    app = build_test_app("postgresql+psycopg://nobody:nothing@localhost:1/none")

    with TestClient(app) as client:
        response = ask(client)

    assert response.status_code == 503
    assert response.json() == {"detail": "Database unavailable."}
