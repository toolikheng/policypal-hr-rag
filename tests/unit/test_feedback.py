"""POST /feedback: in this phase the vote is checked and logged (stored from Phase 4)."""

import json
import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.helpers import build_test_app

# Feedback doesn't touch the database yet; nothing listens on port 1.
NO_DATABASE = "postgresql+psycopg://user:pw@localhost:1/db"
MESSAGE_ID = str(uuid.uuid4())


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(build_test_app(NO_DATABASE)) as client:
        yield client


def test_a_vote_is_accepted(client: TestClient) -> None:
    response = client.post("/feedback", json={"message_id": MESSAGE_ID, "rating": "up"})

    assert response.status_code == 202
    assert response.json() == {"status": "accepted"}


def test_a_vote_is_logged_without_the_comment_text(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level("INFO")
    comment = "Didn't mention site workers, ask Encik Rahman"

    client.post("/feedback", json={"message_id": MESSAGE_ID, "rating": "down", "comment": comment})

    [record] = [r for r in caplog.records if r.getMessage() == "feedback.received"]
    assert (record.message_id, record.rating, record.comment_chars) == (
        MESSAGE_ID,
        "down",
        len(comment),
    )
    assert "Rahman" not in json.dumps(vars(record), default=str)


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"message_id": MESSAGE_ID},
        {"message_id": MESSAGE_ID, "rating": "meh"},
        {"message_id": "not-a-uuid", "rating": "up"},
        {"message_id": MESSAGE_ID, "rating": "up", "comment": "x" * 501},
    ],
    ids=["empty", "no-rating", "bad-rating", "bad-id", "comment-too-long"],
)
def test_invalid_feedback_is_a_422(client: TestClient, payload: dict[str, Any]) -> None:
    assert client.post("/feedback", json=payload).status_code == 422


def test_a_blank_comment_counts_as_no_comment(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level("INFO")

    client.post("/feedback", json={"message_id": MESSAGE_ID, "rating": "up", "comment": "  "})

    [record] = [r for r in caplog.records if r.getMessage() == "feedback.received"]
    assert record.comment_chars == 0
