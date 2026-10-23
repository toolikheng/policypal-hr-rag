"""The Streamlit analytics page, run headless with AppTest and a fake API client."""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from tests.fakes import FakeApiClient
from ui import api_client
from ui.api_client import ApiError

ANALYTICS_PAGE = Path(__file__).resolve().parents[2] / "ui" / "pages" / "2_Analytics.py"

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
SEEDED = {
    "period_days": 30,
    "total_questions": 9,
    "answered": 6,
    "refused": 3,
    "refusal_rate": 0.3333,
    "feedback": {"count": 4, "up": 3, "down": 1, "feedback_rate": 0.4444, "helpful_rate": 0.75},
    "avg_latency_ms": {"overall": 611, "llm": 24300, "extractive": 325},
    "top_questions": [
        {"question": "how much annual leave?", "count": 3, "last_asked": "2026-10-23T08:15:00Z"},
        {"question": "is there a bonus?", "count": 2, "last_asked": "2026-10-22T16:40:00Z"},
    ],
    "unanswered_questions": [
        {"question": "is there a bonus?", "count": 2, "last_asked": "2026-10-22T16:40:00Z"},
    ],
    "fallbacks": [{"reason": "llm_timeout", "count": 2}, {"reason": "llm_unavailable", "count": 1}],
}


def run_page(monkeypatch: pytest.MonkeyPatch, client: FakeApiClient) -> AppTest:
    monkeypatch.setattr(api_client, "make_client", lambda: client)
    return AppTest.from_file(str(ANALYTICS_PAGE), default_timeout=10).run()


def with_token(page: AppTest) -> AppTest:
    return page.text_input(key="analytics_token").input("t0k").run()


def texts(elements) -> list[str]:
    return [element.value for element in elements]


def metrics(page: AppTest) -> dict[str, str]:
    return {metric.label: metric.value for metric in page.metric}


def test_without_a_token_nothing_is_requested(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeApiClient(analytics=SEEDED)

    page = run_page(monkeypatch, client)

    assert texts(page.info) == ["Enter the admin token to see analytics."]
    assert client.calls == []


def test_the_figures_for_the_last_30_days_are_shown(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeApiClient(analytics=SEEDED)

    page = with_token(run_page(monkeypatch, client))

    assert client.calls[-1] == ("analytics", 30, "t0k")
    assert metrics(page) == {
        "Questions": "9",
        "Refused": "3 (33.3%)",
        "Feedback rate": "44.4%",
        "Helpful": "75%",
        "Avg time (all)": "0.6 s",
        "Avg time (AI)": "24.3 s",
        "Avg time (quoted)": "0.3 s",
    }
    top, unanswered, fallbacks = page.dataframe
    assert list(top.value["Question"]) == ["how much annual leave?", "is there a bonus?"]
    assert list(top.value["Times asked"]) == [3, 2]
    assert list(top.value["Last asked"]) == ["2026-10-23 08:15 UTC", "2026-10-22 16:40 UTC"]
    assert list(unanswered.value["Question"]) == ["is there a bonus?"]
    assert list(fallbacks.value["Reason"]) == [
        "the AI model took too long (llm_timeout)",
        "the AI model couldn't be reached (llm_unavailable)",
    ]
    assert list(fallbacks.value["Answers"]) == [2, 1]


def test_an_empty_period_shows_dashes_and_empty_messages(monkeypatch: pytest.MonkeyPatch) -> None:
    page = with_token(run_page(monkeypatch, FakeApiClient(analytics=EMPTY)))

    assert metrics(page)["Refused"] == "0 (—)"
    assert metrics(page)["Helpful"] == "—"
    assert metrics(page)["Avg time (all)"] == "—"
    assert not page.dataframe
    assert {
        "No questions in this period yet.",
        "No refused questions in this period.",
        "No fallbacks in this period.",
    } <= set(texts(page.caption))


def test_choosing_another_period_asks_for_it(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeApiClient(analytics=EMPTY)
    page = with_token(run_page(monkeypatch, client))

    page.selectbox(key="period").select(7).run()

    assert client.calls[-1] == ("analytics", 7, "t0k")


def test_an_api_error_is_shown(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeApiClient(analytics=ApiError("Admin token is not valid.", 403))

    page = with_token(run_page(monkeypatch, client))

    assert texts(page.error) == ["Admin token is not valid."]
    assert not page.metric
