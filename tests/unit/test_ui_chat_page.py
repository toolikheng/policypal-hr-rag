"""The Streamlit chat page, run headless with AppTest and a stubbed API client."""

from pathlib import Path
from typing import Any

import pytest
from streamlit.testing.v1 import AppTest

from ui.api_client import PolicyPalClient

CHAT_PAGE = Path(__file__).resolve().parents[2] / "ui" / "Chat.py"


def run_page(monkeypatch: pytest.MonkeyPatch, health: dict[str, Any]) -> AppTest:
    monkeypatch.setattr(PolicyPalClient, "health", lambda self: health)
    return AppTest.from_file(str(CHAT_PAGE)).run()


def test_healthy_api(monkeypatch: pytest.MonkeyPatch) -> None:
    page = run_page(monkeypatch, {"status": "ok", "database": "ok", "version": "0.1.0"})

    assert page.success[0].value == "API is healthy (version 0.1.0)."


def test_degraded_api_says_answers_quote_the_policies(monkeypatch: pytest.MonkeyPatch) -> None:
    page = run_page(monkeypatch, {"status": "degraded", "database": "ok", "version": "0.1.0"})

    assert page.warning[0].value == (
        "API is up, but the AI model isn't ready: answers will quote the policy text."
    )


def test_unavailable_api_names_the_database_problem(monkeypatch: pytest.MonkeyPatch) -> None:
    page = run_page(
        monkeypatch, {"status": "unavailable", "database": "unreachable", "version": "0.1.0"}
    )

    assert page.warning[0].value == "API is running but not ready: database is unreachable."
