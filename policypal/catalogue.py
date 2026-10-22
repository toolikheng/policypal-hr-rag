"""The policy catalogue: which documents can be searched, and their text by section.

Every read of documents for the API goes through here, so the "document plus its chunk
count" query exists in one place.
"""

from dataclasses import asdict, dataclass
from datetime import datetime
from itertools import groupby
from typing import Any

from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from policypal.ingest.parsing import FileType
from policypal.models import Document, DocumentChunk, Origin


@dataclass(frozen=True)
class DocumentInfo:
    id: int
    slug: str
    title: str
    file_type: FileType
    origin: Origin
    chunks: int
    updated_at: datetime


@dataclass(frozen=True)
class ChunkContents:
    id: int
    text: str


@dataclass(frozen=True)
class SectionContents:
    section: str
    section_path: str
    chunks: tuple[ChunkContents, ...]


@dataclass(frozen=True)
class DocumentContents(DocumentInfo):
    sections: tuple[SectionContents, ...]


def list_documents(engine: Engine) -> list[DocumentInfo]:
    """Every document, ordered by title."""
    return _documents(engine, order_by=(Document.title, Document.id))


def find_document(engine: Engine, slug: str) -> DocumentInfo | None:
    found = _documents(engine, Document.slug == slug)
    return found[0] if found else None


def get_document(engine: Engine, document_id: int) -> DocumentContents | None:
    """A document with its chunks grouped by section, in document order."""
    found = _documents(engine, Document.id == document_id)
    if not found:
        return None
    query = (
        select(
            DocumentChunk.id,
            DocumentChunk.section,
            DocumentChunk.section_path,
            DocumentChunk.content,
        )
        .where(DocumentChunk.document_id == document_id)
        .order_by(DocumentChunk.chunk_index)
    )
    with engine.connect() as conn:
        rows = conn.execute(query).all()
    # A long section is split into several chunks, which are next to each other.
    sections = tuple(
        SectionContents(
            section=section,
            section_path=section_path,
            chunks=tuple(ChunkContents(row.id, row.content) for row in group),
        )
        for (section, section_path), group in groupby(
            rows, key=lambda row: (row.section, row.section_path)
        )
    )
    return DocumentContents(**asdict(found[0]), sections=sections)


def _documents(engine: Engine, *where: Any, order_by: tuple[Any, ...] = ()) -> list[DocumentInfo]:
    """The one "document plus chunk count" query."""
    query = (
        select(Document, func.count(DocumentChunk.id))
        .outerjoin(DocumentChunk, DocumentChunk.document_id == Document.id)
        .where(*where)
        .group_by(Document.id)
        .order_by(*order_by)
    )
    with Session(engine) as session:
        return [
            DocumentInfo(
                id=document.id,
                slug=document.slug,
                title=document.title,
                file_type=document.file_type,
                origin=document.origin,
                chunks=chunks,
                updated_at=document.updated_at,
            )
            for document, chunks in session.execute(query)
        ]
