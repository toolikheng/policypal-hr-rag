"""The Streamlit admin page, run headless with AppTest and a fake API client."""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from tests.fakes import FakeApiClient
from ui import api_client
from ui.api_client import ApiError

ADMIN_PAGE = Path(__file__).resolve().parents[2] / "ui" / "pages" / "1_Admin.py"

DOCUMENTS = {
    3: {"id": 3, "slug": "leave-policy", "title": "Leave Policy", "file_type": "md",
        "origin": "sample", "chunks": 20, "updated_at": "2026-10-22T09:30:00Z"},
}  # fmt: skip
FILE = ("training-and-development-policy.md", b"# Training", "text/markdown")
CREATED = {"status": "created", "document": {"title": "Training Policy", "chunks": 11}}
UPDATED = {"status": "updated", "document": {"title": "Training Policy", "chunks": 12}}
NAME_TAKEN = ApiError("A policy named 'x' already exists ...", 409, "name_taken")
SAMPLE = ApiError("'leave-policy' is a built-in sample policy ...", 409, "sample_policy")


def run_page(monkeypatch: pytest.MonkeyPatch, client: FakeApiClient) -> AppTest:
    monkeypatch.setattr(api_client, "make_client", lambda: client)
    return AppTest.from_file(str(ADMIN_PAGE), default_timeout=10).run()


def with_token_and_file(page: AppTest) -> AppTest:
    page.text_input(key="admin_token").input("t0k").run()
    page.get("file_uploader")[0].set_value(FILE)  # type: ignore[attr-defined]
    return page.run()


def texts(elements) -> list[str]:
    return [element.value for element in elements]


def uploads(client: FakeApiClient) -> list[tuple]:
    return [call for call in client.calls if call[0] == "upload"]


def test_without_a_token_only_the_documents_are_shown(monkeypatch: pytest.MonkeyPatch) -> None:
    page = run_page(monkeypatch, FakeApiClient(documents=DOCUMENTS))

    assert texts(page.info) == ["Enter the admin token to upload or re-ingest policies."]
    assert page.button(key="upload").disabled
    assert page.button(key="reingest").disabled
    [table] = page.dataframe
    assert list(table.value["Title"]) == ["Leave Policy"]
    assert list(table.value["Origin"]) == ["sample"]


def test_uploading_a_new_policy_shows_the_result(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeApiClient(documents=DOCUMENTS, uploads=[CREATED])
    page = with_token_and_file(run_page(monkeypatch, client))

    page = page.button(key="upload").click().run()

    assert uploads(client) == [("upload", FILE[0], FILE[1], "t0k", False)]
    assert texts(page.success) == ["Training Policy: created (11 chunks)."]


def test_a_conflict_with_an_uploaded_policy_offers_replace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = FakeApiClient(uploads=[NAME_TAKEN, UPDATED])
    page = with_token_and_file(run_page(monkeypatch, client))
    page = page.button(key="upload").click().run()

    assert texts(page.warning) == ["A policy named 'x' already exists ..."]

    page = page.button(key="replace").click().run()

    assert uploads(client)[-1] == ("upload", FILE[0], FILE[1], "t0k", True)
    assert texts(page.success) == ["Training Policy: updated (12 chunks)."]
    assert not page.warning


def test_a_sample_policy_conflict_has_no_replace_button(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = with_token_and_file(run_page(monkeypatch, FakeApiClient(uploads=[SAMPLE])))

    page = page.button(key="upload").click().run()

    assert texts(page.warning) == ["'leave-policy' is a built-in sample policy ..."]
    assert not [button for button in page.button if button.key == "replace"]


@pytest.mark.parametrize(
    "error",
    [
        ApiError("Only .md and .pdf files are supported.", 415),
        ApiError("Admin token is not valid.", 403),
    ],
)
def test_upload_errors_are_shown(monkeypatch: pytest.MonkeyPatch, error: ApiError) -> None:
    page = with_token_and_file(run_page(monkeypatch, FakeApiClient(uploads=[error])))

    page = page.button(key="upload").click().run()

    assert texts(page.error) == [str(error)]


def test_reingest_shows_a_summary(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeApiClient()
    page = run_page(monkeypatch, client)
    page.text_input(key="admin_token").input("t0k").run()

    page = page.button(key="reingest").click().run()

    assert ("reingest", "t0k") in client.calls
    assert texts(page.success) == ["Re-ingested 1 policy: 1 unchanged."]


def test_a_reingest_with_files_not_loaded_is_a_warning_not_a_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    results = [
        {"slug": "leave-policy", "status": "unchanged", "chunks": 20},
        {"slug": "broken-policy", "status": "failed", "chunks": 0},
    ]
    page = run_page(monkeypatch, FakeApiClient(reingests=[results]))
    page.text_input(key="admin_token").input("t0k").run()

    page = page.button(key="reingest").click().run()

    assert texts(page.warning) == [
        "Re-ingested 2 policies: 1 unchanged, 1 failed. Not loaded: broken-policy (failed)."
    ]
    assert not page.success


def test_reingest_errors_are_shown(monkeypatch: pytest.MonkeyPatch) -> None:
    error = ApiError("Admin token is not valid.", 403)
    page = run_page(monkeypatch, FakeApiClient(reingests=[error]))
    page.text_input(key="admin_token").input("t0k").run()

    page = page.button(key="reingest").click().run()

    assert texts(page.error) == ["Admin token is not valid."]
