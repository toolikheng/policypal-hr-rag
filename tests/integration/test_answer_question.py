"""answer_question end to end: database search, then the answering rules, with timings."""

import pytest
from sqlalchemy import Engine

from policypal.answering import answer_question
from policypal.ingest.pipeline import SAMPLE_POLICIES_DIR, ingest_file
from policypal.retrieval import retrieve
from tests.fakes import FakeEmbedder, FakeLLM


@pytest.fixture
def embedder(engine: Engine) -> FakeEmbedder:
    embedder = FakeEmbedder()
    ingest_file(engine, embedder, SAMPLE_POLICIES_DIR / "leave-policy.md", origin="sample")
    return embedder


def test_retrieves_then_answers_and_times_each_step(engine: Engine, embedder: FakeEmbedder) -> None:
    llm = FakeLLM("You get 16 days [1].")
    question = "How many days of annual leave do I get?"
    expected = retrieve(engine, FakeEmbedder(), question, top_k=3)

    answer = answer_question(
        question, engine=engine, embedder=embedder, llm=llm, top_k=3, min_similarity=0.0
    )

    assert answer.reply.mode == "llm"
    assert answer.reply.citations[0].chunk == expected[0]
    assert llm.calls == [(question, expected)]
    assert answer.top_similarity == expected[0].similarity
    assert answer.retrieval_ms >= 0
    assert answer.reply.generation_ms is not None
    assert answer.total_ms >= answer.retrieval_ms


def test_empty_database_is_a_refusal_with_no_similarity(engine: Engine) -> None:
    answer = answer_question(
        "Anything?",
        engine=engine,
        embedder=FakeEmbedder(),
        llm=FakeLLM(),
        top_k=5,
        min_similarity=0.65,
    )

    assert answer.reply.mode == "refused"
    assert answer.top_similarity is None


def ranked(answer) -> list[tuple[int, int, bool]]:
    return [(s.rank, s.chunk.chunk_id, s.cited) for s in answer.sources]


def test_answer_lists_every_retrieved_chunk_with_its_rank_and_whether_it_was_cited(
    engine: Engine, embedder: FakeEmbedder
) -> None:
    question = "How many days of annual leave do I get?"
    expected = retrieve(engine, FakeEmbedder(), question, top_k=4)

    answer = answer_question(
        question,
        engine=engine,
        embedder=embedder,
        llm=FakeLLM("Sixteen days [2], carried forward [4]."),
        top_k=4,
        min_similarity=0.0,
    )

    assert [s.chunk for s in answer.sources] == expected
    assert [(rank, cited) for rank, _, cited in ranked(answer)] == [
        (1, False),
        (2, True),
        (3, False),
        (4, True),
    ]


def test_a_citation_number_is_the_search_rank_of_its_chunk(
    engine: Engine, embedder: FakeEmbedder
) -> None:
    answer = answer_question(
        "How many days of annual leave do I get?",
        engine=engine,
        embedder=embedder,
        llm=None,  # extractive: quotes the top three
        top_k=5,
        min_similarity=0.0,
    )

    assert [c.number for c in answer.reply.citations] == [1, 2, 3]
    for citation in answer.reply.citations:
        assert answer.sources[citation.number - 1].chunk == citation.chunk
    assert [s.cited for s in answer.sources] == [True, True, True, False, False]


def test_a_refusal_still_lists_what_was_retrieved(engine: Engine, embedder: FakeEmbedder) -> None:
    answer = answer_question(
        "How many days of annual leave do I get?",
        engine=engine,
        embedder=embedder,
        llm=FakeLLM(),
        top_k=3,
        min_similarity=0.99,
    )

    assert answer.reply.mode == "refused"
    assert len(answer.sources) == 3
    assert not any(s.cited for s in answer.sources)
    assert answer.top_similarity == answer.sources[0].chunk.similarity
