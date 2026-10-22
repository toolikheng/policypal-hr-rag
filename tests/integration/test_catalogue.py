"""The policy catalogue: which documents are searchable, and their text section by section."""

import shutil
from pathlib import Path

import pytest
from sqlalchemy import Engine, text

from policypal import catalogue
from policypal.ingest.pipeline import SAMPLE_POLICIES_DIR, IngestResult, ingest_folder
from tests.fakes import FakeEmbedder


@pytest.fixture
def ingested(engine: Engine, tmp_path: Path) -> dict[str, int]:
    """Two sample policies; returns chunk counts by slug."""
    folder = tmp_path / "policies"
    folder.mkdir()
    for slug in ("overtime-policy", "leave-policy"):
        shutil.copy(SAMPLE_POLICIES_DIR / f"{slug}.md", folder)
    results: list[IngestResult] = ingest_folder(engine, FakeEmbedder(), folder, origin="sample")
    return {result.slug: result.chunks for result in results}


def test_empty_catalogue_lists_nothing(engine: Engine) -> None:
    assert catalogue.list_documents(engine) == []


def test_lists_documents_by_title_with_their_chunk_counts(
    engine: Engine, ingested: dict[str, int]
) -> None:
    documents = catalogue.list_documents(engine)

    assert [d.title for d in documents] == ["Leave Policy", "Overtime Policy"]
    assert {d.slug: d.chunks for d in documents} == ingested
    assert {(d.file_type, d.origin) for d in documents} == {("md", "sample")}
    assert all(d.updated_at is not None for d in documents)


def test_finds_a_document_by_slug(engine: Engine, ingested: dict[str, int]) -> None:
    leave = catalogue.find_document(engine, "leave-policy")

    assert leave is not None
    assert (leave.slug, leave.title, leave.chunks) == (
        "leave-policy",
        "Leave Policy",
        ingested["leave-policy"],
    )
    assert catalogue.find_document(engine, "no-such-policy") is None


def test_document_contents_are_grouped_by_section_in_order(
    engine: Engine, ingested: dict[str, int]
) -> None:
    leave = catalogue.find_document(engine, "leave-policy")
    assert leave is not None

    contents = catalogue.get_document(engine, leave.id)

    assert contents is not None
    assert (contents.id, contents.slug, contents.chunks) == (leave.id, leave.slug, leave.chunks)
    with engine.connect() as conn:
        stored = conn.execute(
            text(
                "SELECT id, section, section_path, content FROM chunks"
                " WHERE document_id = :id ORDER BY chunk_index"
            ),
            {"id": leave.id},
        ).all()
    shown = [
        (chunk.id, section.section, section.section_path, chunk.text)
        for section in contents.sections
        for chunk in section.chunks
    ]
    assert shown == [tuple(row) for row in stored]
    paths = [section.section_path for section in contents.sections]
    assert len(paths) == len(set(paths)), "each section appears once"


def test_unknown_document_has_no_contents(engine: Engine) -> None:
    assert catalogue.get_document(engine, 999999) is None
