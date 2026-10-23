"""Saving answers to the question history (policypal.history) on the real database."""

import uuid

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError

from policypal.answering import Answer
from policypal.history import save_answer
from policypal.ingest.pipeline import SAMPLE_POLICIES_DIR, ingest_file
from policypal.llm.base import REFUSAL_SENTENCE
from policypal.retrieval import RetrievedChunk
from tests.fakes import FakeEmbedder
from tests.helpers import make_answer, retrieved_chunk

QUESTION = "How many days of annual leave do I get?"


def leave_chunks(engine: Engine, count: int) -> list[RetrievedChunk]:
    """Real chunks of the Leave Policy, shaped as search results (best first)."""
    ingest_file(engine, FakeEmbedder(), SAMPLE_POLICIES_DIR / "leave-policy.md", origin="sample")
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT c.id, c.document_id, d.title, c.section, c.section_path, c.content"
                " FROM chunks c JOIN documents d ON d.id = c.document_id"
                " ORDER BY c.chunk_index LIMIT :count"
            ),
            {"count": count},
        ).all()
    return [
        retrieved_chunk(
            chunk_id=row.id,
            document_id=row.document_id,
            title=row.title,
            section=row.section,
            section_path=row.section_path,
            text=row.content,
            similarity=0.8 - rank / 10,
        )
        for rank, row in enumerate(rows)
    ]


def llm_answer(chunks: list[RetrievedChunk]) -> Answer:
    """An LLM answer that cites only the second chunk."""
    return make_answer(
        "llm",
        sources=chunks,
        cited=[2],
        text="You get 16 days [1].",
        model="tiny:1b",
        retrieval_ms=40,
        generation_ms=900,
        total_ms=950,
    )


def message_row(engine: Engine, message_id: uuid.UUID):
    with engine.connect() as conn:
        return conn.execute(text("SELECT * FROM messages WHERE id = :id"), {"id": message_id}).one()


def source_rows(engine: Engine, message_id: uuid.UUID):
    with engine.connect() as conn:
        return conn.execute(
            text("SELECT * FROM message_sources WHERE message_id = :id ORDER BY rank"),
            {"id": message_id},
        ).all()


def count(engine: Engine, table: str) -> int:
    with engine.connect() as conn:
        return conn.execute(text(f"SELECT count(*) FROM {table}")).scalar_one()  # noqa: S608


def test_an_answer_is_saved_with_its_mode_model_and_timings(engine: Engine) -> None:
    chunks = leave_chunks(engine, 3)

    saved = save_answer(engine, QUESTION, llm_answer(chunks), channel="ui")

    row = message_row(engine, saved.message_id)
    assert row.conversation_id == saved.conversation_id
    assert (row.question, row.answer, row.mode) == (QUESTION, "You get 16 days [1].", "llm")
    assert (row.llm_model, row.fallback_reason) == ("tiny:1b", None)
    assert row.top_similarity == pytest.approx(0.8)
    assert (row.retrieval_ms, row.generation_ms, row.total_ms) == (40, 900, 950)
    assert row.created_at is not None


def test_every_retrieved_source_is_saved_with_rank_snapshot_and_cited_flag(
    engine: Engine,
) -> None:
    chunks = leave_chunks(engine, 3)

    saved = save_answer(engine, QUESTION, llm_answer(chunks), channel="ui")

    rows = source_rows(engine, saved.message_id)
    assert [row.rank for row in rows] == [1, 2, 3]
    assert [row.chunk_id for row in rows] == [chunk.chunk_id for chunk in chunks]
    assert [row.cited for row in rows] == [False, True, False]
    assert [(row.document_title, row.section) for row in rows] == [
        (chunk.document_title, chunk.section) for chunk in chunks
    ]
    assert [row.similarity for row in rows] == pytest.approx([0.8, 0.7, 0.6])


def test_a_refusal_is_saved_with_what_was_retrieved(engine: Engine) -> None:
    chunks = leave_chunks(engine, 2)

    saved = save_answer(engine, QUESTION, make_answer(sources=chunks), channel="api")

    row = message_row(engine, saved.message_id)
    assert (row.answer, row.mode, row.llm_model, row.generation_ms) == (
        REFUSAL_SENTENCE,
        "refused",
        None,
        None,
    )
    assert [source.cited for source in source_rows(engine, saved.message_id)] == [False, False]


def test_a_refusal_with_nothing_retrieved_has_no_sources(engine: Engine) -> None:
    saved = save_answer(engine, QUESTION, make_answer(), channel="api")

    assert message_row(engine, saved.message_id).top_similarity is None
    assert source_rows(engine, saved.message_id) == []


def test_without_a_conversation_id_a_new_conversation_is_created(engine: Engine) -> None:
    first = save_answer(engine, QUESTION, make_answer(), channel="ui")
    second = save_answer(engine, QUESTION, make_answer(), channel="ui")

    assert first.conversation_id != second.conversation_id
    with engine.connect() as conn:
        channels = conn.execute(text("SELECT channel FROM conversations")).scalars().all()
    assert channels == ["ui", "ui"]


def test_a_known_conversation_id_groups_the_messages(engine: Engine) -> None:
    first = save_answer(engine, QUESTION, make_answer(), channel="ui")
    second = save_answer(
        engine, QUESTION, make_answer(), conversation_id=first.conversation_id, channel="ui"
    )

    assert second.conversation_id == first.conversation_id
    assert second.message_id != first.message_id
    assert (count(engine, "conversations"), count(engine, "messages")) == (1, 2)


def test_an_unknown_conversation_id_is_created_with_that_id(engine: Engine) -> None:
    """Owner decision A: a client (e.g. the widget) may make up its own conversation ID."""
    conversation_id = uuid.uuid4()

    saved = save_answer(
        engine, QUESTION, make_answer(), conversation_id=conversation_id, channel="widget"
    )

    assert saved.conversation_id == conversation_id
    with engine.connect() as conn:
        channel = conn.execute(
            text("SELECT channel FROM conversations WHERE id = :id"), {"id": conversation_id}
        ).scalar_one()
    assert channel == "widget"


def test_a_chunk_deleted_after_retrieval_is_saved_as_null_with_its_snapshot(
    engine: Engine,
) -> None:
    """A re-ingest can replace a policy's chunks while a question is being answered."""
    chunks = leave_chunks(engine, 3)
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM chunks WHERE id = :id"), {"id": chunks[0].chunk_id})

    saved = save_answer(engine, QUESTION, llm_answer(chunks), channel="ui")

    rows = source_rows(engine, saved.message_id)
    assert [row.chunk_id for row in rows] == [None, chunks[1].chunk_id, chunks[2].chunk_id]
    assert rows[0].section == chunks[0].section


def test_the_message_and_its_sources_are_saved_all_or_nothing(engine: Engine) -> None:
    broken = retrieved_chunk(chunk_id=999, title=None)  # type: ignore[arg-type]
    answer = make_answer(sources=[broken])

    with pytest.raises(IntegrityError):
        save_answer(engine, QUESTION, answer, channel="ui")

    assert (count(engine, "conversations"), count(engine, "messages")) == (0, 0)
