"""Small helpers shared by tests (fixtures live in conftest.py)."""

from alembic.config import Config

from policypal.config import Settings
from policypal.retrieval import RetrievedChunk


def alembic_config(database_url: str) -> Config:
    config = Config("alembic.ini")
    config.attributes["database_url"] = database_url
    return config


def make_settings(database_url: str) -> Settings:
    # _env_file=None: tests must not depend on a developer's local .env file.
    return Settings(_env_file=None, database_url=database_url)


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
