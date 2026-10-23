"""POST /feedback stores one vote per answer; voting again replaces it."""

import json
import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from policypal.history import save_answer
from tests.helpers import build_test_app, make_answer


@pytest.fixture
def client(migrated_database_url: str, engine: Engine) -> Iterator[TestClient]:
    with TestClient(build_test_app(migrated_database_url)) as client:
        yield client


@pytest.fixture
def message_id(engine: Engine) -> str:
    saved = save_answer(engine, "Is there a bonus?", make_answer(), channel="ui")
    return str(saved.message_id)


def vote(client: TestClient, message_id: str, rating: str, comment: str | None = None):
    return client.post(
        "/feedback", json={"message_id": message_id, "rating": rating, "comment": comment}
    )


def stored_votes(engine: Engine) -> list[Any]:
    with engine.connect() as conn:
        return conn.execute(
            text("SELECT message_id, rating, comment, created_at, updated_at FROM feedback")
        ).all()


def test_a_vote_is_stored(client: TestClient, engine: Engine, message_id: str) -> None:
    response = vote(client, message_id, "down", "Didn't mention site workers")

    assert response.status_code == 200
    assert response.json() == {"status": "recorded"}
    [stored] = stored_votes(engine)
    assert (str(stored.message_id), stored.rating, stored.comment) == (
        message_id,
        "down",
        "Didn't mention site workers",
    )


def test_voting_again_replaces_the_vote(
    client: TestClient, engine: Engine, message_id: str
) -> None:
    vote(client, message_id, "down", "Wrong grade")
    [first] = stored_votes(engine)

    response = vote(client, message_id, "up")

    assert response.status_code == 200
    [stored] = stored_votes(engine)
    assert (stored.rating, stored.comment) == ("up", None)
    assert stored.created_at == first.created_at
    assert stored.updated_at > first.updated_at


def test_a_blank_comment_is_stored_as_no_comment(
    client: TestClient, engine: Engine, message_id: str
) -> None:
    vote(client, message_id, "up", "   ")

    [stored] = stored_votes(engine)
    assert stored.comment is None


def test_a_vote_for_an_unknown_message_is_a_404(client: TestClient, engine: Engine) -> None:
    response = vote(client, str(uuid.uuid4()), "up")

    assert response.status_code == 404
    assert response.json() == {"detail": "Message not found."}
    assert stored_votes(engine) == []


def test_a_vote_is_logged_without_the_comment_text(
    client: TestClient, message_id: str, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level("INFO")
    comment = "Didn't mention site workers, ask Encik Rahman"

    vote(client, message_id, "down", comment)

    [record] = [r for r in caplog.records if r.getMessage() == "feedback.recorded"]
    assert (record.message_id, record.rating, record.comment_chars) == (
        message_id,
        "down",
        len(comment),
    )
    assert "Rahman" not in json.dumps(vars(record), default=str)


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"message_id": "6f1c2a9e-3b1d-4c55-9a51-2f0f7d1e8b3a"},
        {"message_id": "6f1c2a9e-3b1d-4c55-9a51-2f0f7d1e8b3a", "rating": "meh"},
        {"message_id": "not-a-uuid", "rating": "up"},
        {
            "message_id": "6f1c2a9e-3b1d-4c55-9a51-2f0f7d1e8b3a",
            "rating": "up",
            "comment": "x" * 501,
        },
        # PostgreSQL text can't hold the NUL character, so it's rejected, not a 500.
        {
            "message_id": "6f1c2a9e-3b1d-4c55-9a51-2f0f7d1e8b3a",
            "rating": "up",
            "comment": "a\u0000b",
        },
    ],
    ids=["empty", "no-rating", "bad-rating", "bad-id", "comment-too-long", "comment-with-nul"],
)
def test_invalid_feedback_is_a_422(client: TestClient, payload: dict[str, Any]) -> None:
    assert client.post("/feedback", json=payload).status_code == 422


def test_database_down_is_a_503() -> None:
    app = build_test_app("postgresql+psycopg://nobody:nothing@localhost:1/none")
    with TestClient(app) as client:
        response = vote(client, str(uuid.uuid4()), "up")

    assert response.status_code == 503
