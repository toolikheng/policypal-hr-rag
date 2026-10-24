"""The embeddable chat widget: plain JavaScript files served by the API at /widget/.

The widget is checked by hand in a browser (README). These tests check that it is served
and guard the rules that keep it safe and countable.
"""

import re

import pytest
from fastapi.testclient import TestClient

from policypal.api.main import WIDGET_DIR
from tests.helpers import NO_DATABASE, build_test_app

SCRIPT = (WIDGET_DIR / "policypal-widget.js").read_text(encoding="utf-8")


@pytest.fixture
def client() -> TestClient:
    return TestClient(build_test_app(NO_DATABASE))


def test_the_widget_script_is_served(client: TestClient) -> None:
    response = client.get("/widget/policypal-widget.js")

    assert response.status_code == 200
    assert "javascript" in response.headers["content-type"]
    assert response.text == SCRIPT


def test_the_demo_page_is_served_and_loads_the_widget(client: TestClient) -> None:
    response = client.get("/widget/demo.html")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert '<script src="policypal-widget.js"' in response.text
    assert "fictional" in response.text.lower()


def test_other_paths_under_widget_are_not_found(client: TestClient) -> None:
    assert client.get("/widget/missing.js").status_code == 404
    assert client.get("/widget/../policypal/config.py").status_code == 404


def test_the_widget_never_turns_text_into_html() -> None:
    # Answers and citations come from the LLM and from policy files, which can be uploaded.
    # Text is only ever set with textContent, so it can't run as HTML or script (XSS).
    for unsafe in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval("):
        assert unsafe not in SCRIPT, unsafe
    assert "textContent" in SCRIPT


def test_the_widget_asks_as_the_widget_channel() -> None:
    # Analytics can then tell widget questions from UI and API ones.
    assert re.search(r'channel:\s*"widget"', SCRIPT)
    assert '"/ask"' in SCRIPT
