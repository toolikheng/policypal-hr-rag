"""Small helpers shared by tests (fixtures live in conftest.py)."""

from typing import Any

from alembic.config import Config
from fastapi import FastAPI

from policypal.api.main import create_app
from policypal.config import Settings
from policypal.embeddings import Embedder
from policypal.llm.base import LLMProvider
from policypal.retrieval import RetrievedChunk
from tests.fakes import FakeEmbedder, FakeLLM


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
