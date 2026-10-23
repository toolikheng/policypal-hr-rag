"""GET /analytics: admin only, `days` from 1 to 365, and the JSON shape."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from policypal.answering import Answer, Reply
from policypal.history import record_feedback, save_answer
from policypal.llm.base import REFUSAL_SENTENCE
from tests.helpers import build_test_app

TOKEN = "test-admin-token"
ADMIN = {"X-Admin-Token": TOKEN}

EMPTY = {
    "period_days": 30,
    "total_questions": 0,
    "answered": 0,
    "refused": 0,
    "refusal_rate": None,
    "feedback": {"count": 0, "up": 0, "down": 0, "feedback_rate": None, "helpful_rate": None},
    "avg_latency_ms": {"overall": None, "llm": None, "extractive": None},
    "top_questions": [],
    "unanswered_questions": [],
    "fallbacks": [],
}


@pytest.fixture
def client(migrated_database_url: str, engine: Engine) -> Iterator[TestClient]:
    with TestClient(build_test_app(migrated_database_url, admin_token=TOKEN)) as client:
        yield client


def test_an_empty_database_gives_the_empty_state(client: TestClient) -> None:
    response = client.get("/analytics", headers=ADMIN)

    assert response.status_code == 200
    assert response.json() == EMPTY


def test_the_period_defaults_to_30_days_and_can_be_changed(client: TestClient) -> None:
    response = client.get("/analytics", params={"days": 7}, headers=ADMIN)

    assert response.json()["period_days"] == 7


def test_stored_questions_and_votes_are_reported(client: TestClient, engine: Engine) -> None:
    refusal = Answer(Reply(REFUSAL_SENTENCE, "refused"), (), retrieval_ms=5, total_ms=20)
    saved = save_answer(engine, "Is there a bonus?", refusal, conversation_id=None, channel="ui")
    record_feedback(engine, saved.message_id, "down", None)
    fallback = Answer(
        Reply("quoted", "extractive", fallback_reason="llm_timeout", generation_ms=120000),
        (),
        retrieval_ms=5,
        total_ms=120010,
    )
    save_answer(engine, "Dress code?", fallback, conversation_id=None, channel="ui")

    body = client.get("/analytics", headers=ADMIN).json()

    assert (body["total_questions"], body["answered"], body["refused"]) == (2, 1, 1)
    assert body["refusal_rate"] == 0.5
    assert body["feedback"] == {
        "count": 1,
        "up": 0,
        "down": 1,
        "feedback_rate": 0.5,
        "helpful_rate": 0.0,
    }
    assert body["avg_latency_ms"] == {"overall": 60015, "llm": None, "extractive": 120010}
    [unanswered] = body["unanswered_questions"]
    assert (unanswered["question"], unanswered["count"]) == ("is there a bonus?", 1)
    assert unanswered["last_asked"]
    assert body["fallbacks"] == [{"reason": "llm_timeout", "count": 1}]


@pytest.mark.parametrize("days", [0, 366, "month"])
def test_days_outside_1_to_365_is_a_422(client: TestClient, days: object) -> None:
    assert client.get("/analytics", params={"days": days}, headers=ADMIN).status_code == 422


@pytest.mark.parametrize(
    ("headers", "status"), [({}, 401), ({"X-Admin-Token": "guess"}, 403)], ids=["none", "wrong"]
)
def test_the_admin_token_is_required(
    client: TestClient, headers: dict[str, str], status: int
) -> None:
    assert client.get("/analytics", headers=headers).status_code == status


def test_analytics_is_off_without_an_admin_token_setting(migrated_database_url: str) -> None:
    with TestClient(build_test_app(migrated_database_url)) as client:
        assert client.get("/analytics", headers=ADMIN).status_code == 503


def test_an_old_fallback_reason_the_code_no_longer_has_is_shown_as_it_is(
    client: TestClient, engine: Engine
) -> None:
    """Stored rows outlive the code: renaming a reason must never break analytics."""
    with engine.begin() as conn:
        conversation_id = conn.execute(
            text("INSERT INTO conversations (channel) VALUES ('ui') RETURNING id")
        ).scalar_one()
        conn.execute(
            text(
                "INSERT INTO messages (conversation_id, question, answer, mode, fallback_reason,"
                " retrieval_ms, total_ms) VALUES (:id, 'Dress code?', 'quoted', 'extractive',"
                " 'ollama_timeout', 5, 60005)"
            ),
            {"id": conversation_id},
        )

    response = client.get("/analytics", headers=ADMIN)

    assert response.status_code == 200
    assert response.json()["fallbacks"] == [{"reason": "ollama_timeout", "count": 1}]
