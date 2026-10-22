"""Vector search over the stored chunks, using the deterministic FakeEmbedder."""

import shutil
from pathlib import Path

import pytest
from sqlalchemy import Engine, text

from policypal.ingest.pipeline import SAMPLE_POLICIES_DIR, ingest_folder
from policypal.retrieval import retrieve
from tests.fakes import FakeEmbedder


@pytest.fixture
def embedder(engine: Engine, tmp_path: Path) -> FakeEmbedder:
    """Two sample policies ingested with the fake embedder."""
    folder = tmp_path / "policies"
    folder.mkdir()
    for slug in ("leave-policy", "overtime-policy"):
        shutil.copy(SAMPLE_POLICIES_DIR / f"{slug}.md", folder)
    embedder = FakeEmbedder()
    ingest_folder(engine, embedder, folder, origin="sample")
    return embedder


def stored_chunks(engine: Engine) -> list:
    with engine.connect() as conn:
        return conn.execute(
            text(
                "SELECT c.id, c.document_id, d.title, c.section, c.section_path, c.content"
                " FROM chunks c JOIN documents d ON d.id = c.document_id ORDER BY c.id"
            )
        ).all()


def test_question_is_embedded_as_a_query(engine: Engine, embedder: FakeEmbedder) -> None:
    retrieve(engine, embedder, "How is overtime paid on a rest day?", top_k=5)

    assert embedder.embedded_queries == ["How is overtime paid on a rest day?"]


def test_best_match_comes_first_with_its_citation_details(
    engine: Engine, embedder: FakeEmbedder
) -> None:
    target = stored_chunks(engine)[7]
    # The fake embedder gives identical text an identical vector, so this chunk must win.
    question = f"{target.title} — {target.section_path}\n{target.content}"

    [best, *_] = retrieve(engine, embedder, question, top_k=5)

    assert best.chunk_id == target.id
    assert best.document_id == target.document_id
    assert best.document_title == target.title
    assert best.section == target.section
    assert best.section_path == target.section_path
    assert best.text == target.content
    assert best.similarity == pytest.approx(1.0, abs=1e-6)


def test_returns_top_k_results_in_order_of_similarity(
    engine: Engine, embedder: FakeEmbedder
) -> None:
    results = retrieve(engine, embedder, "annual leave carry forward days", top_k=3)

    assert len(results) == 3
    similarities = [result.similarity for result in results]
    assert similarities == sorted(similarities, reverse=True)


def test_similarity_is_the_cosine_similarity_of_the_vectors(
    engine: Engine, embedder: FakeEmbedder
) -> None:
    question = "Who approves overtime work?"
    query_vector = FakeEmbedder().embed_query(question)

    results = retrieve(engine, embedder, question, top_k=5)

    for result in results:
        chunk_vector = FakeEmbedder().embed_documents(
            [f"{result.document_title} — {result.section_path}\n{result.text}"]
        )[0]
        # Both vectors have length 1, so cosine similarity is their dot product.
        expected = sum(q * c for q, c in zip(query_vector, chunk_vector, strict=True))
        assert result.similarity == pytest.approx(expected, abs=1e-5)


def test_empty_database_returns_no_results(engine: Engine) -> None:
    assert retrieve(engine, FakeEmbedder(), "Any question at all?", top_k=5) == []
