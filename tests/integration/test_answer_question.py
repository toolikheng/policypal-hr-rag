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
