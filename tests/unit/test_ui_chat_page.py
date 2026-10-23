"""The Streamlit chat page, run headless with AppTest and a fake API client."""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from tests.fakes import FakeApiClient
from ui import api_client
from ui.api_client import ApiError

CHAT_PAGE = Path(__file__).resolve().parents[2] / "ui" / "Chat.py"

LEAVE_TEXT = "| Years | E grades |\n|---|---|\n| 2 to 5 | 16 days |"
ANSWER = {
    "message_id": "m-1",
    "conversation_id": "c-1",
    "answer": "After 3 years E grades get 16 days [1].",
    "mode": "llm",
    "refused": False,
    "citations": [
        {
            "number": 1,
            "document_id": 3,
            "document_title": "Leave Policy",
            "section": "4.1 Annual Leave Entitlement",
            "text": LEAVE_TEXT,
            "similarity": 0.7723,
        }
    ],
    "model": "llama3.2:3b",
    "fallback_reason": None,
    "latency_ms": {"retrieval": 40, "generation": 9000, "total": 9040},
}
REFUSAL = {
    **ANSWER,
    "message_id": "m-2",
    "answer": "I couldn't find this in the policies.",
    "mode": "refused",
    "refused": True,
    "citations": [],
    "model": None,
}
LEAVE_DOCUMENT = {
    "id": 3,
    "title": "Leave Policy",
    "sections": [
        {
            "section": "4.1 Annual Leave Entitlement",
            "section_path": "4. Annual Leave > 4.1 Annual Leave Entitlement",
            "chunks": [{"id": 41, "text": "Annual leave depends on grade.\n\n" + LEAVE_TEXT}],
        }
    ],
}


def run_page(monkeypatch: pytest.MonkeyPatch, client: FakeApiClient) -> AppTest:
    monkeypatch.setattr(api_client, "make_client", lambda: client)
    return AppTest.from_file(str(CHAT_PAGE), default_timeout=10).run()


def ask(page: AppTest, question: str) -> AppTest:
    page.chat_input[0].set_value(question)
    return page.run()


def texts(elements) -> list[str]:
    return [element.value for element in elements]


# --- Health ---------------------------------------------------------------------------


def test_a_healthy_api_shows_no_warning(monkeypatch: pytest.MonkeyPatch) -> None:
    page = run_page(monkeypatch, FakeApiClient())

    assert not page.warning and not page.error
    assert page.chat_input


def test_degraded_api_says_answers_quote_the_policies(monkeypatch: pytest.MonkeyPatch) -> None:
    health = {"status": "degraded", "database": "ok", "version": "0.1.0"}

    page = run_page(monkeypatch, FakeApiClient(health=health))

    assert texts(page.warning) == ["The AI model isn't ready: answers will quote the policy text."]


def test_unavailable_api_names_the_database_problem(monkeypatch: pytest.MonkeyPatch) -> None:
    health = {"status": "unavailable", "database": "unreachable", "version": "0.1.0"}

    page = run_page(monkeypatch, FakeApiClient(health=health))

    assert texts(page.error) == ["The API is running but not ready: database is unreachable."]


def test_unreachable_api_shows_the_error_and_no_chat(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeApiClient(health=ApiError("Cannot reach the PolicyPal API at http://api:8000."))

    page = run_page(monkeypatch, client)

    assert texts(page.error) == ["Cannot reach the PolicyPal API at http://api:8000."]
    assert not page.chat_input


# --- Asking ----------------------------------------------------------------------------


def test_an_answer_shows_its_badge_text_and_sources(monkeypatch: pytest.MonkeyPatch) -> None:
    page = run_page(monkeypatch, FakeApiClient(answers=[ANSWER]))

    page = ask(page, "How much annual leave after 3 years?")

    assert "How much annual leave after 3 years?" in texts(page.markdown)
    assert "After 3 years E grades get 16 days [1]." in texts(page.markdown)
    assert "🤖 AI answer from the policies (llama3.2:3b)" in texts(page.caption)
    [source] = page.expander
    assert source.label == "[1] Leave Policy — 4.1 Annual Leave Entitlement · 0.77"
    assert LEAVE_TEXT in texts(source.markdown)


def test_the_conversation_id_is_kept_between_questions(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeApiClient(answers=[ANSWER, REFUSAL])
    page = run_page(monkeypatch, client)

    ask(ask(page, "First?"), "Second?")

    assert [call for call in client.calls if call[0] == "ask"] == [
        ("ask", "First?", None),
        ("ask", "Second?", "c-1"),
    ]


def test_a_refusal_shows_no_sources(monkeypatch: pytest.MonkeyPatch) -> None:
    page = ask(run_page(monkeypatch, FakeApiClient(answers=[REFUSAL])), "Bonus?")

    assert "I couldn't find this in the policies." in texts(page.markdown)
    assert "🚫 Not covered by the policies" in texts(page.caption)
    assert not page.expander


def test_a_failed_question_shows_the_error_and_keeps_the_history(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = FakeApiClient(answers=[ANSWER, ApiError("The PolicyPal API took too long.")])
    page = ask(run_page(monkeypatch, client), "First?")

    page = ask(page, "Second?")

    assert "The PolicyPal API took too long." in texts(page.error)
    assert "After 3 years E grades get 16 days [1]." in texts(page.markdown)


def test_view_full_section_shows_the_whole_section(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeApiClient(answers=[ANSWER], documents={3: LEAVE_DOCUMENT})
    page = ask(run_page(monkeypatch, client), "Leave?")

    page = page.button(key="section-0-1").click().run()

    assert ("get_document", 3) in client.calls
    assert "Annual leave depends on grade.\n\n" + LEAVE_TEXT in texts(page.markdown)


# --- Feedback ----------------------------------------------------------------------------


@pytest.mark.parametrize(("key", "rating"), [("up-0", "up"), ("down-0", "down")])
def test_a_vote_reaches_the_api_once(
    monkeypatch: pytest.MonkeyPatch, key: str, rating: str
) -> None:
    client = FakeApiClient(answers=[ANSWER])
    page = ask(run_page(monkeypatch, client), "Leave?")

    page = page.button(key=key).click().run()

    assert [call for call in client.calls if call[0] == "feedback"] == [
        ("feedback", "m-1", rating, None)
    ]
    assert "Thanks for your feedback." in texts(page.caption)
    assert not [button for button in page.button if button.key in ("up-0", "down-0")]


def test_a_failed_vote_shows_the_error(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeApiClient(answers=[ANSWER])
    page = ask(run_page(monkeypatch, client), "Leave?")

    def broken_feedback(*args: object, **kwargs: object) -> None:
        raise ApiError("Cannot reach the PolicyPal API at http://api:8000.")

    client.feedback = broken_feedback  # type: ignore[method-assign]
    page = page.button(key="up-0").click().run()

    assert "Cannot reach the PolicyPal API at http://api:8000." in texts(page.error)
