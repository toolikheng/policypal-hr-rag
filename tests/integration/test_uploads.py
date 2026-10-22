"""POST /documents (upload) and POST /documents/reingest, including the 409 conflict rules."""

import hashlib
import io
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from policypal.ingest.pipeline import SAMPLE_POLICIES_DIR, ingest_file
from policypal.ingest.uploads import FileTooLarge, UploadConflict, UploadResult, add_upload
from tests.fakes import FakeEmbedder
from tests.helpers import build_test_app
from tests.sample_data import UPLOAD_DEMO_POLICY

TOKEN = "test-admin-token"
ADMIN = {"X-Admin-Token": TOKEN}
DEMO_BYTES = UPLOAD_DEMO_POLICY.read_bytes()
DEMO_SLUG = "training-and-development-policy"
SAMPLE_LEAVE = SAMPLE_POLICIES_DIR / "leave-policy.md"
EDITED_DEMO = DEMO_BYTES + b"\n## 11. New Clause\n\nA new rule added later.\n"

CONFLICT_MESSAGE = (
    "A policy named 'training-and-development-policy' already exists with different content."
    " Nothing was changed. To replace it, upload again with replace=true."
)
SAMPLE_MESSAGE = (
    "'leave-policy' is a built-in sample policy and can't be replaced by upload."
    " Rename the file to add it as a new policy."
)


@pytest.fixture
def upload_dir(tmp_path: Path) -> Path:
    return tmp_path / "uploads"


@pytest.fixture
def client(migrated_database_url: str, engine: Engine, upload_dir: Path) -> Iterator[TestClient]:
    app = build_test_app(
        migrated_database_url, admin_token=TOKEN, upload_dir=upload_dir, max_upload_mb=1
    )
    with TestClient(app) as client:
        yield client


@pytest.fixture
def sample_leave(engine: Engine) -> None:
    ingest_file(engine, FakeEmbedder(), SAMPLE_LEAVE, origin="sample")


def upload(
    client: TestClient,
    data: bytes = DEMO_BYTES,
    filename: str = f"{DEMO_SLUG}.md",
    headers: dict[str, str] | None = None,
    **params: Any,
) -> httpx.Response:
    return client.post(
        "/documents",
        files={"file": (filename, data, "application/octet-stream")},
        params=params,
        headers=ADMIN if headers is None else headers,
    )


def snapshot(engine: Engine, upload_dir: Path) -> dict[str, Any]:
    """Everything an upload could change: document rows, chunks and saved files."""
    with engine.connect() as conn:
        documents = conn.execute(
            text("SELECT slug, origin, content_sha256, updated_at FROM documents ORDER BY slug")
        ).all()
        chunks = conn.execute(text("SELECT id, document_id, content FROM chunks ORDER BY id")).all()
    files = {}
    if upload_dir.exists():
        files = {path.name: path.read_bytes() for path in sorted(upload_dir.iterdir())}
    return {"documents": documents, "chunks": chunks, "files": files}


def chunk_indexes(engine: Engine, slug: str) -> list[int]:
    with engine.connect() as conn:
        return list(
            conn.execute(
                text(
                    "SELECT c.chunk_index FROM chunks c JOIN documents d ON d.id = c.document_id"
                    " WHERE d.slug = :slug ORDER BY c.chunk_index"
                ),
                {"slug": slug},
            ).scalars()
        )


# --- Admin token ------------------------------------------------------------------------

ADMIN_ENDPOINTS = [
    ("upload", lambda client, headers: upload(client, headers=headers)),
    ("reingest", lambda client, headers: client.post("/documents/reingest", headers=headers)),
]


@pytest.mark.parametrize(("name", "call"), ADMIN_ENDPOINTS, ids=[n for n, _ in ADMIN_ENDPOINTS])
def test_admin_endpoints_need_the_token(client: TestClient, name: str, call: Any) -> None:
    missing = call(client, {})
    wrong = call(client, {"X-Admin-Token": "guess"})

    assert missing.status_code == 401
    assert missing.json() == {"detail": "Admin token required in the X-Admin-Token header."}
    assert wrong.status_code == 403
    assert wrong.json() == {"detail": "Admin token is not valid."}


@pytest.mark.parametrize(("name", "call"), ADMIN_ENDPOINTS, ids=[n for n, _ in ADMIN_ENDPOINTS])
def test_admin_endpoints_are_off_without_an_admin_token_setting(
    migrated_database_url: str, upload_dir: Path, name: str, call: Any
) -> None:
    app = build_test_app(migrated_database_url, upload_dir=upload_dir)

    with TestClient(app) as client:
        response = call(client, ADMIN)

    assert response.status_code == 503
    assert response.json() == {"detail": "Admin features are disabled: set ADMIN_TOKEN."}


# --- Checking the file --------------------------------------------------------------


BAD_FILES = {
    "wrong-type": ("notes.txt", b"# Notes", 415, "Only .md and .pdf files are supported."),
    "too-large": ("big.md", b"#" * (1024 * 1024 + 1), 413, "The file is larger than 1 MB."),
    "not-a-pdf": ("fake.pdf", b"# Not a PDF", 422, "The file is not a valid PDF."),
    "broken-pdf": ("broken.pdf", b"%PDF-1.4 garbage", 422, "The file is not a readable PDF."),
    "not-utf8": (
        "latin1.md",
        "# Política\n\n## 1. Á\n\nTexto.".encode("latin-1"),
        422,
        "The Markdown file is not valid UTF-8 text.",
    ),
    "no-title": (
        "untitled.md",
        b"Just some text without a title.",
        422,
        "The Markdown file has no title line ('# Title').",
    ),
    "no-name": ("!!!.md", DEMO_BYTES, 422, "The file name must contain letters or digits."),
}


@pytest.mark.parametrize(
    ("filename", "data", "status", "detail"), BAD_FILES.values(), ids=BAD_FILES.keys()
)
def test_bad_files_are_rejected_and_nothing_is_saved(
    client: TestClient,
    engine: Engine,
    upload_dir: Path,
    filename: str,
    data: bytes,
    status: int,
    detail: str,
) -> None:
    before = snapshot(engine, upload_dir)

    response = upload(client, data, filename)

    assert response.status_code == status
    assert response.json() == {"detail": detail}
    assert snapshot(engine, upload_dir) == before


# --- The conflict rules -----------------------------------------------------------------


def test_new_policy_is_created_and_saved(
    client: TestClient, engine: Engine, upload_dir: Path
) -> None:
    response = upload(client)

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "created"
    document = body["document"]
    assert document["slug"] == DEMO_SLUG
    assert document["title"] == "Training and Development Policy"
    assert document["origin"] == "upload"
    assert document["file_type"] == "md"
    assert document["chunks"] == len(chunk_indexes(engine, DEMO_SLUG)) > 0
    assert (upload_dir / f"{DEMO_SLUG}.md").read_bytes() == DEMO_BYTES
    assert [d["slug"] for d in client.get("/documents").json()] == [DEMO_SLUG]


def test_same_file_again_is_unchanged(client: TestClient, engine: Engine, upload_dir: Path) -> None:
    upload(client)
    before = snapshot(engine, upload_dir)

    response = upload(client)

    assert response.status_code == 200
    assert response.json()["status"] == "unchanged"
    assert snapshot(engine, upload_dir) == before


def test_different_content_for_an_existing_upload_is_a_409_and_changes_nothing(
    client: TestClient, engine: Engine, upload_dir: Path
) -> None:
    upload(client)
    before = snapshot(engine, upload_dir)

    response = upload(client, EDITED_DEMO)

    assert response.status_code == 409
    assert response.json() == {"detail": CONFLICT_MESSAGE}
    assert snapshot(engine, upload_dir) == before


def test_replace_true_replaces_the_chunks_without_duplicates(
    client: TestClient, engine: Engine, upload_dir: Path
) -> None:
    first = upload(client).json()["document"]

    response = upload(client, EDITED_DEMO, replace="true")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "updated"
    assert body["document"]["id"] == first["id"]
    assert body["document"]["chunks"] == first["chunks"] + 1
    assert chunk_indexes(engine, DEMO_SLUG) == list(range(first["chunks"] + 1))
    assert (upload_dir / f"{DEMO_SLUG}.md").read_bytes() == EDITED_DEMO


def test_replacing_with_a_pdf_keeps_one_file_per_policy(
    client: TestClient, upload_dir: Path
) -> None:
    upload(client)
    pdf = UPLOAD_DEMO_POLICY.with_suffix(".pdf").read_bytes()

    response = upload(client, pdf, f"{DEMO_SLUG}.pdf", replace="true")

    assert response.json()["document"]["file_type"] == "pdf"
    assert sorted(p.name for p in upload_dir.iterdir()) == [f"{DEMO_SLUG}.pdf"]


@pytest.mark.parametrize("replace", ["false", "true"])
def test_a_sample_policy_can_never_be_replaced_by_upload(
    client: TestClient, engine: Engine, upload_dir: Path, sample_leave: None, replace: str
) -> None:
    before = snapshot(engine, upload_dir)
    edited = SAMPLE_LEAVE.read_bytes() + b"\nEdited.\n"

    response = upload(client, edited, "leave-policy.md", replace=replace)

    assert response.status_code == 409
    assert response.json() == {"detail": SAMPLE_MESSAGE}
    assert snapshot(engine, upload_dir) == before


def test_a_sample_policy_in_another_format_is_also_protected(
    client: TestClient, sample_leave: None
) -> None:
    pdf = (SAMPLE_POLICIES_DIR / "pdf" / "leave-policy.pdf").read_bytes()

    response = upload(client, pdf, "leave-policy.pdf", replace="true")

    assert response.status_code == 409


def test_uploading_an_unchanged_sample_policy_saves_nothing(
    client: TestClient, engine: Engine, upload_dir: Path, sample_leave: None
) -> None:
    before = snapshot(engine, upload_dir)

    response = upload(client, SAMPLE_LEAVE.read_bytes(), "leave-policy.md")

    assert response.status_code == 200
    assert response.json()["status"] == "unchanged"
    assert response.json()["document"]["origin"] == "sample"
    assert snapshot(engine, upload_dir) == before


def test_file_is_saved_under_its_slug(client: TestClient, upload_dir: Path) -> None:
    response = upload(client, filename="Training and Development Policy.MD")

    assert response.json()["document"]["slug"] == DEMO_SLUG
    assert [p.name for p in upload_dir.iterdir()] == [f"{DEMO_SLUG}.md"]


def add(
    engine: Engine,
    upload_dir: Path,
    data: bytes = DEMO_BYTES,
    *,
    embedder: FakeEmbedder | None = None,
    replace: bool = False,
) -> UploadResult:
    """add_upload() called directly, without HTTP, with a 1 MB limit."""
    return add_upload(
        engine,
        embedder or FakeEmbedder(),
        upload_dir,
        f"{DEMO_SLUG}.md",
        io.BytesIO(data),
        replace=replace,
        max_mb=1,
    )


def test_add_upload_returns_the_stored_document(engine: Engine, upload_dir: Path) -> None:
    result = add(engine, upload_dir)

    assert result.status == "created"
    assert result.document.slug == DEMO_SLUG
    assert result.document.title == "Training and Development Policy"
    assert result.document.origin == "upload"
    assert result.document.chunks == len(chunk_indexes(engine, DEMO_SLUG))


def test_size_limit_is_part_of_the_upload_rules(engine: Engine, upload_dir: Path) -> None:
    with pytest.raises(FileTooLarge, match="The file is larger than 1 MB."):
        add(engine, upload_dir, b"#" * (1024 * 1024 + 1))
    assert not upload_dir.exists()


def test_an_oversized_upload_is_never_read_past_the_limit(engine: Engine, upload_dir: Path) -> None:
    stream = io.BytesIO(b"#" * (3 * 1024 * 1024))

    with pytest.raises(FileTooLarge):
        add_upload(engine, FakeEmbedder(), upload_dir, "big.md", stream, replace=False, max_mb=1)

    assert stream.tell() == 1024 * 1024 + 1


def test_same_bytes_after_a_pipeline_change_are_re_embedded_not_a_conflict(
    engine: Engine, upload_dir: Path
) -> None:
    add(engine, upload_dir, embedder=FakeEmbedder(model_name="model-a"))
    model_b = FakeEmbedder(model_name="model-b")

    result = add(engine, upload_dir, embedder=model_b)

    assert result.status == "updated"
    assert model_b.embedded_texts  # stale vectors from model-a were replaced


class SlowEmbedder(FakeEmbedder):
    """Slow enough that two uploads overlap if nothing stops them."""

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        time.sleep(0.2)
        return super().embed_documents(texts)


def test_two_uploads_of_one_new_policy_at_once_cannot_both_win(
    engine: Engine, upload_dir: Path
) -> None:
    outcomes: list[str] = []

    def try_upload(data: bytes) -> None:
        try:
            add(engine, upload_dir, data, embedder=SlowEmbedder())
            outcomes.append("created")
        except UploadConflict:
            outcomes.append("conflict")

    threads = [threading.Thread(target=try_upload, args=(d,)) for d in (DEMO_BYTES, EDITED_DEMO)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert sorted(outcomes) == ["conflict", "created"]
    assert len(list(upload_dir.iterdir())) == 1


# --- Re-ingest ------------------------------------------------------------------------


def statuses(results: list[dict[str, Any]]) -> dict[str, str]:
    return {result["slug"]: result["status"] for result in results}


def test_reingest_rescans_both_folders_without_duplicates(
    client: TestClient, engine: Engine, upload_dir: Path
) -> None:
    upload(client)

    first = client.post("/documents/reingest", headers=ADMIN)
    before = snapshot(engine, upload_dir)
    second = client.post("/documents/reingest", headers=ADMIN)

    assert first.status_code == second.status_code == 200
    assert len(statuses(first.json()["results"])) == 9  # 8 samples + 1 upload
    assert set(statuses(second.json()["results"]).values()) == {"unchanged"}
    assert snapshot(engine, upload_dir) == before


def test_reingest_removes_an_upload_whose_file_was_deleted(
    client: TestClient, upload_dir: Path
) -> None:
    upload(client)
    (upload_dir / f"{DEMO_SLUG}.md").unlink()

    results = client.post("/documents/reingest", headers=ADMIN).json()["results"]

    assert statuses(results)[DEMO_SLUG] == "removed"


def test_sample_wins_when_an_uploaded_file_has_a_sample_slug(
    client: TestClient, engine: Engine, upload_dir: Path
) -> None:
    client.post("/documents/reingest", headers=ADMIN)
    upload_dir.mkdir(exist_ok=True)
    (upload_dir / "leave-policy.md").write_bytes(SAMPLE_LEAVE.read_bytes() + b"\nOther text.\n")

    results = client.post("/documents/reingest", headers=ADMIN).json()["results"]

    assert {"slug": "leave-policy", "status": "skipped", "chunks": 0} in results
    with engine.connect() as conn:
        origin, sha = conn.execute(
            text("SELECT origin, content_sha256 FROM documents WHERE slug = 'leave-policy'")
        ).one()
    assert origin == "sample"
    assert sha == hashlib.sha256(SAMPLE_LEAVE.read_bytes()).hexdigest()
