"""Add an uploaded policy without ever replacing one by accident.

The rules, checked before anything is saved:
- A file that isn't .md or .pdf, or can't be read as a policy, is rejected.
- The same bytes as an existing policy change nothing ("unchanged").
- A built-in sample policy is never replaced: the sample folder is re-ingested on
  every start, so an upload of the same name couldn't stick anyway.
- Different content under the name of an uploaded policy is a conflict, unless the
  caller asks to replace it.
Only then is the file saved to the upload folder (as <slug>.md or <slug>.pdf) and
ingested, which also makes it survive a restart.
"""

import hashlib
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from policypal.catalogue import DocumentInfo, find_document
from policypal.embeddings import Embedder
from policypal.ingest.parsing import SUPPORTED_SUFFIXES, FileType, parse_document
from policypal.ingest.pipeline import IngestResult, ingest_all, ingest_file, slug_for
from policypal.models import Document, DocumentChunk

# Uploads and re-scans check the database, then write files and rows. Running them one
# at a time means two requests can't both pass the conflict check. (The API runs as one
# process; the database's unique slug is the last line of defence.)
_write_lock = threading.Lock()


@dataclass(frozen=True)
class UploadResult:
    status: Literal["created", "updated", "unchanged"]
    document: DocumentInfo  # the document as stored after the upload


class UploadRejected(Exception):
    """The upload was refused. The message is safe to show to the user."""


class UnsupportedFileType(UploadRejected):
    pass


class InvalidUpload(UploadRejected):
    pass


class UploadConflict(UploadRejected):
    pass


def add_upload(
    engine: Engine,
    embedder: Embedder,
    upload_dir: Path,
    filename: str,
    data: bytes,
    *,
    replace: bool,
) -> UploadResult:
    """Check, save and ingest one uploaded file. Raises an UploadRejected subclass."""
    file_type = SUPPORTED_SUFFIXES.get(Path(filename).suffix.lower())
    if file_type is None:
        raise UnsupportedFileType("Only .md and .pdf files are supported.")
    slug = slug_for(Path(filename))
    if not slug:
        raise InvalidUpload("The file name must contain letters or digits.")
    _check_content(data, file_type)
    content_sha256 = hashlib.sha256(data).hexdigest()

    with _write_lock:
        existing = _find(engine, slug)
        if existing is not None:
            origin, existing_sha256, _ = existing
            if existing_sha256 == content_sha256:
                return UploadResult("unchanged", _stored(engine, slug))
            if origin == "sample":
                raise UploadConflict(
                    f"'{slug}' is a built-in sample policy and can't be replaced by upload."
                    " Rename the file to add it as a new policy."
                )
            if not replace:
                raise UploadConflict(
                    f"A policy named '{slug}' already exists with different content."
                    " Nothing was changed. To replace it, upload again with replace=true."
                )
        path = _save(upload_dir, slug, file_type, data)
        result = ingest_file(engine, embedder, path, origin="upload")
        # A new slug is "created"; an existing one passed the checks above, so "updated".
        status = "created" if result.status == "created" else "updated"
        return UploadResult(status, _stored(engine, slug))


def rescan(engine: Engine, embedder: Embedder, upload_dir: Path) -> list[IngestResult]:
    """Re-ingest the sample and upload folders (no duplicates; unchanged files are skipped)."""
    with _write_lock:
        return ingest_all(engine, embedder, upload_dir)


def _stored(engine: Engine, slug: str) -> DocumentInfo:
    document = find_document(engine, slug)
    if document is None:  # it was found or stored a moment ago, under the lock
        raise RuntimeError(f"Document '{slug}' disappeared during the upload.")
    return document


def _check_content(data: bytes, file_type: FileType) -> None:
    if file_type == "pdf" and not data.startswith(b"%PDF-"):
        raise InvalidUpload("The file is not a valid PDF.")
    try:
        parse_document(data, file_type)
    except ValueError as exc:  # the parser's messages are written for users
        raise InvalidUpload(str(exc)) from exc


def _find(engine: Engine, slug: str) -> tuple[str, str, int] | None:
    """(origin, content_sha256, chunk count) of the document with this slug, if any."""
    query = (
        select(Document.origin, Document.content_sha256, func.count(DocumentChunk.id))
        .outerjoin(DocumentChunk, DocumentChunk.document_id == Document.id)
        .where(Document.slug == slug)
        .group_by(Document.id)
    )
    with Session(engine) as session:
        row = session.execute(query).first()
    return None if row is None else (row[0], row[1], row[2])


def _save(upload_dir: Path, slug: str, file_type: FileType, data: bytes) -> Path:
    """Save as <slug>.<type>, replacing the policy's previous file (in either format)."""
    upload_dir.mkdir(parents=True, exist_ok=True)
    path = upload_dir / f"{slug}.{file_type}"
    # Write to a temporary name, then rename: the folder never holds a half-written policy.
    temporary = upload_dir / f".{path.name}.tmp"
    temporary.write_bytes(data)
    temporary.replace(path)
    for other in upload_dir.iterdir():
        if other != path and other.suffix.lower() in SUPPORTED_SUFFIXES and slug_for(other) == slug:
            other.unlink()
    return path
