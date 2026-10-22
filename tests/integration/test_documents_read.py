"""GET /documents and GET /documents/{id}: list the policies and show one, section by section."""

import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from policypal.ingest.pipeline import SAMPLE_POLICIES_DIR, IngestResult, ingest_folder
from tests.fakes import FakeEmbedder, FakeLLM
from tests.helpers import build_test_app


@pytest.fixture
def ingested(engine: Engine, tmp_path: Path) -> list[IngestResult]:
    folder = tmp_path / "policies"
    folder.mkdir()
    for slug in ("overtime-policy", "leave-policy"):
        shutil.copy(SAMPLE_POLICIES_DIR / f"{slug}.md", folder)
    return ingest_folder(engine, FakeEmbedder(), folder, origin="sample")


def document_id(engine: Engine, slug: str) -> int:
    with engine.connect() as conn:
        query = text("SELECT id FROM documents WHERE slug = :slug")
        return conn.execute(query, {"slug": slug}).scalar_one()


def test_no_documents_is_an_empty_list(client: TestClient, engine: Engine) -> None:
    response = client.get("/documents")

    assert response.status_code == 200
    assert response.json() == []


def test_lists_documents_by_title_with_their_chunk_counts(
    client: TestClient, engine: Engine, ingested: list[IngestResult]
) -> None:
    body = client.get("/documents").json()

    assert [d["title"] for d in body] == ["Leave Policy", "Overtime Policy"]
    chunks = {result.slug: result.chunks for result in ingested}
    for document in body:
        assert document["id"] == document_id(engine, document["slug"])
        assert document["chunks"] == chunks[document["slug"]]
        assert document["file_type"] == "md"
        assert document["origin"] == "sample"
        assert document["updated_at"]


def test_document_shows_every_chunk_grouped_by_section_in_order(
    client: TestClient, engine: Engine, ingested: list[IngestResult]
) -> None:
    leave_id = document_id(engine, "leave-policy")

    response = client.get(f"/documents/{leave_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "Leave Policy"
    assert body["slug"] == "leave-policy"
    with engine.connect() as conn:
        stored = conn.execute(
            text(
                "SELECT id, section, section_path, content FROM chunks"
                " WHERE document_id = :id ORDER BY chunk_index"
            ),
            {"id": leave_id},
        ).all()
    shown = [
        (chunk["id"], section["section"], section["section_path"], chunk["text"])
        for section in body["sections"]
        for chunk in section["chunks"]
    ]
    assert shown == [tuple(row) for row in stored]
    assert body["chunks"] == len(stored)
    paths = [section["section_path"] for section in body["sections"]]
    assert len(paths) == len(set(paths)), "each section appears once"


def test_every_citation_can_be_opened_in_its_document(
    migrated_database_url: str, ingested: list[IngestResult]
) -> None:
    llm = FakeLLM("Overtime needs approval [1] and pays more [2].")
    app = build_test_app(migrated_database_url, llm=llm, min_similarity=0.1)

    with TestClient(app) as client:
        citations = client.post("/ask", json={"question": "Who approves overtime?"}).json()[
            "citations"
        ]
        assert len(citations) == 2
        for citation in citations:
            document = client.get(f"/documents/{citation['document_id']}").json()
            texts = {
                (section["section"], chunk["text"])
                for section in document["sections"]
                for chunk in section["chunks"]
            }
            assert (citation["section"], citation["text"]) in texts


def test_unknown_document_is_a_404(client: TestClient, engine: Engine) -> None:
    response = client.get("/documents/999999")

    assert response.status_code == 404
    assert response.json() == {"detail": "Document not found."}


def test_non_numeric_document_id_is_a_422(client: TestClient) -> None:
    assert client.get("/documents/leave-policy").status_code == 422
