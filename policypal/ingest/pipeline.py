"""Load policy files into the database: parse -> chunk -> embed -> store.

Ingestion is idempotent, so it is safe to run on every start:
- a file whose bytes and pipeline version haven't changed is skipped (nothing re-embedded);
- a new or changed file replaces all of its document's chunks in one transaction;
- a document whose file has disappeared from its folder is removed.
"""

import hashlib
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from sqlalchemy import Engine, delete, func, select
from sqlalchemy.orm import Session

from policypal.embeddings import Embedder, check_dimension
from policypal.ingest.chunking import CHUNKER_VERSION, chunk_document, embedding_text
from policypal.ingest.parsing import SUPPORTED_SUFFIXES, file_type_of, parse_document
from policypal.models import Document, DocumentChunk, Origin

logger = logging.getLogger("policypal.ingest")

SAMPLE_POLICIES_DIR = Path(__file__).resolve().parents[2] / "data" / "policies"

IngestStatus = Literal["created", "updated", "unchanged", "removed"]


@dataclass(frozen=True)
class IngestResult:
    slug: str
    status: IngestStatus
    chunks: int


def ingest_folder(
    engine: Engine, embedder: Embedder, folder: Path, origin: Origin
) -> list[IngestResult]:
    """Ingest every .md/.pdf file directly inside `folder` (not sub-folders), then remove
    documents of the same origin whose file is no longer there."""
    files = sorted(path for path in folder.iterdir() if path.suffix.lower() in SUPPORTED_SUFFIXES)
    results = [ingest_file(engine, embedder, path, origin) for path in files]
    return results + _remove_missing(engine, origin, keep={result.slug for result in results})


def ingest_file(engine: Engine, embedder: Embedder, path: Path, origin: Origin) -> IngestResult:
    """Ingest one file and log the outcome (created, updated or unchanged)."""
    result = _ingest_file(engine, embedder, path, origin)
    _log(result)
    return result


def _ingest_file(engine: Engine, embedder: Embedder, path: Path, origin: Origin) -> IngestResult:
    file_type = file_type_of(path.name)
    check_dimension(embedder)

    data = path.read_bytes()
    slug = slug_for(path)
    content_sha256 = hashlib.sha256(data).hexdigest()
    version = pipeline_version(embedder)

    with Session(engine) as session, session.begin():
        document = session.scalar(select(Document).where(Document.slug == slug))
        unchanged = (
            document is not None
            and document.content_sha256 == content_sha256
            and document.pipeline_version == version
        )
        if unchanged:
            return IngestResult(slug, "unchanged", _chunk_count(session, document.id))

        parsed = parse_document(data, file_type)
        chunks = chunk_document(parsed)
        vectors = embedder.embed_documents([embedding_text(parsed.title, c) for c in chunks])

        status: IngestStatus = "updated" if document else "created"
        if document is None:
            document = Document(slug=slug)
            session.add(document)
        document.title = parsed.title
        document.source_filename = path.name
        document.file_type = file_type
        document.origin = origin
        document.content_sha256 = content_sha256
        document.pipeline_version = version
        session.flush()  # gives a new document its id

        session.execute(delete(DocumentChunk).where(DocumentChunk.document_id == document.id))
        session.add_all(
            DocumentChunk(
                document_id=document.id,
                chunk_index=chunk.index,
                section=chunk.section,
                section_path=chunk.section_path,
                content=chunk.content,
                word_count=chunk.word_count,
                embedding=vector,
            )
            for chunk, vector in zip(chunks, vectors, strict=True)
        )
    return IngestResult(slug, status, len(chunks))


def slug_for(path: Path) -> str:
    """'Leave Policy (v3).md' -> 'leave-policy-v3'. The slug identifies a document."""
    return re.sub(r"[^a-z0-9]+", "-", path.stem.lower()).strip("-")


def pipeline_version(embedder: Embedder) -> str:
    """Changes whenever stored vectors would be different, which forces re-embedding."""
    return f"{embedder.model_name}|chunker-v{CHUNKER_VERSION}"


def _chunk_count(session: Session, document_id: int) -> int:
    query = select(func.count()).where(DocumentChunk.document_id == document_id)
    return session.scalar(query) or 0


def _remove_missing(engine: Engine, origin: Origin, keep: set[str]) -> list[IngestResult]:
    with Session(engine) as session, session.begin():
        missing = session.scalars(
            select(Document).where(Document.origin == origin, Document.slug.not_in(keep))
        ).all()
        for document in missing:
            session.delete(document)  # its chunks go too (ON DELETE CASCADE)
    results = [IngestResult(document.slug, "removed", 0) for document in missing]
    for result in results:
        _log(result)
    return results


def _log(result: IngestResult) -> None:
    logger.info(
        "ingest.document",
        extra={"slug": result.slug, "status": result.status, "chunks": result.chunks},
    )
