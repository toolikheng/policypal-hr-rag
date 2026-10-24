"""Small helpers shared by tests (fixtures live in conftest.py)."""

from collections.abc import Collection, Sequence
from pathlib import Path
from typing import Any

from alembic.config import Config
from fastapi import FastAPI

from policypal.answering import Answer, Citation, Reply, Source
from policypal.api.main import create_app
from policypal.config import Settings
from policypal.embeddings import Embedder
from policypal.llm.base import REFUSAL_SENTENCE, LLMProvider
from policypal.retrieval import RetrievedChunk
from policypal.vocabulary import FallbackReason, Mode
from tests.fakes import FakeEmbedder, FakeLLM

REPO_ROOT = Path(__file__).resolve().parents[1]
ENV_EXAMPLE = REPO_ROOT / ".env.example"
# A database URL nothing listens on (port 1), for tests that never touch the database.
NO_DATABASE = "postgresql+psycopg://user:pw@localhost:1/db"


def alembic_config(database_url: str) -> Config:
    config = Config("alembic.ini")
    config.attributes["database_url"] = database_url
    return config


def make_settings(database_url: str, **overrides: Any) -> Settings:
    # _env_file=None: tests must not depend on a developer's local .env file.
    return Settings(_env_file=None, database_url=database_url, **overrides)


def build_test_app(
    database_url: str,
    *,
    llm: LLMProvider | None = None,
    embedder: Embedder | None = None,
    **settings: Any,
) -> FastAPI:
    """The app wired with test doubles, so no model is loaded and no network is used.

    The embedder is a FakeEmbedder and the LLM a FakeLLM unless given. For extractive
    mode, pass llm_provider="extractive" (the app then has no LLM at all).
    """
    app_settings = make_settings(database_url, **settings)
    if llm is None and app_settings.llm_provider != "extractive":
        llm = FakeLLM()
    return create_app(app_settings, embedder=embedder or FakeEmbedder(), llm=llm)


def retrieved_chunk(
    *,
    chunk_id: int = 1,
    document_id: int = 1,
    title: str = "Leave Policy",
    section: str = "4.1 Annual Leave Entitlement",
    section_path: str = "4. Annual Leave > 4.1 Annual Leave Entitlement",
    text: str = "Employees get 16 days of annual leave.",
    similarity: float = 0.8,
) -> RetrievedChunk:
    """A search result for unit tests, without a database."""
    return RetrievedChunk(
        chunk_id=chunk_id,
        document_id=document_id,
        document_title=title,
        section=section,
        section_path=section_path,
        text=text,
        similarity=similarity,
    )


def make_answer(
    mode: Mode = "refused",
    *,
    sources: Sequence[RetrievedChunk] = (),
    cited: Collection[int] = (),
    text: str | None = None,
    model: str | None = None,
    fallback_reason: FallbackReason | None = None,
    retrieval_ms: int = 5,
    generation_ms: int | None = None,
    total_ms: int = 10,
) -> Answer:
    """A finished answer, as answer_question() returns it, without retrieval or an LLM.

    `sources` are the retrieved chunks, best first; `cited` lists the ranks shown to the
    user as citations [1], [2], ... in that order.
    """
    citations = tuple(Citation(number, sources[rank - 1]) for number, rank in enumerate(cited, 1))
    reply = Reply(
        text=text or (REFUSAL_SENTENCE if mode == "refused" else "An answer [1]."),
        mode=mode,
        citations=citations,
        model=model,
        fallback_reason=fallback_reason,
        generation_ms=generation_ms,
    )
    return Answer(
        reply=reply,
        sources=tuple(
            Source(rank, chunk, rank in cited) for rank, chunk in enumerate(sources, start=1)
        ),
        retrieval_ms=retrieval_ms,
        total_ms=total_ms,
    )
