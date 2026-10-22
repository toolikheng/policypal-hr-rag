"""Add an uploaded policy without ever replacing one by accident.

The rules, checked before anything is saved:
- A file that is too large, isn't .md or .pdf, or can't be read as a policy is rejected.
- What the file means for the stored policy is decided by pipeline.classify(), the same
  rule the folder scan uses:
  - the same bytes as an existing policy change nothing ("unchanged");
  - a built-in sample policy is never replaced (the sample folder is re-ingested on
    every start, so an upload of the same name couldn't stick anyway);
  - different content under the name of an uploaded policy is a conflict, unless the
    caller asks to replace it.
Only then is the file saved to the upload folder (as <slug>.md or <slug>.pdf) and
ingested, which also makes it survive a restart.
"""

import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from sqlalchemy import Engine

from policypal.catalogue import DocumentInfo, find_document
from policypal.embeddings import Embedder
from policypal.ingest.parsing import SUPPORTED_SUFFIXES, FileType, file_type_of, parse_document
from policypal.ingest.pipeline import (
    IngestResult,
    classify_file,
    ingest_all,
    ingest_file,
    slug_for,
)

MEGABYTE = 1024 * 1024

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


class FileTooLarge(UploadRejected):
    pass


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
    max_bytes: int,
) -> UploadResult:
    """Check, save and ingest one uploaded file. Raises an UploadRejected subclass."""
    if len(data) > max_bytes:
        raise FileTooLarge(f"The file is larger than {max_bytes / MEGABYTE:g} MB.")
    try:
        file_type = file_type_of(filename)
    except ValueError as exc:
        raise UnsupportedFileType("Only .md and .pdf files are supported.") from exc
    slug = slug_for(Path(filename))
    if not slug:
        raise InvalidUpload("The file name must contain letters or digits.")
    _check_content(data, file_type)

    with _write_lock:
        change = classify_file(engine, embedder, slug, data, origin="upload")
        if change == "same":
            return UploadResult("unchanged", _stored(engine, slug))
        if change == "sample_owns_slug":
            raise UploadConflict(
                f"'{slug}' is a built-in sample policy and can't be replaced by upload."
                " Rename the file to add it as a new policy."
            )
        if change == "new_content" and not replace:
            raise UploadConflict(
                f"A policy named '{slug}' already exists with different content."
                " Nothing was changed. To replace it, upload again with replace=true."
            )
        path = _save(upload_dir, slug, file_type, data)
        ingest_file(engine, embedder, path, origin="upload")
        return UploadResult("created" if change == "new" else "updated", _stored(engine, slug))


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
