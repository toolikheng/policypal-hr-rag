import json
import shutil
from pathlib import Path

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import OperationalError

from policypal.db import make_engine
from policypal.ingest import __main__ as ingest_cli
from policypal.ingest import pipeline
from policypal.ingest.chunking import chunk_document
from policypal.ingest.parsing import parse_markdown
from policypal.ingest.pipeline import SAMPLE_POLICIES_DIR, ingest_file, ingest_folder
from tests.fakes import FakeEmbedder
from tests.sample_data import UPLOAD_DEMO_POLICY


@pytest.fixture
def policy_folder(tmp_path: Path) -> Path:
    folder = tmp_path / "policies"
    folder.mkdir()
    for slug in ("leave-policy", "overtime-policy"):
        shutil.copy(SAMPLE_POLICIES_DIR / f"{slug}.md", folder)
    return folder


def counts(engine: Engine) -> tuple[int, int]:
    with engine.connect() as conn:
        documents = conn.execute(text("SELECT count(*) FROM documents")).scalar_one()
        chunks = conn.execute(text("SELECT count(*) FROM chunks")).scalar_one()
    return documents, chunks


def statuses(results) -> dict[str, str]:
    return {result.slug: result.status for result in results}


def test_first_ingest_creates_documents_and_chunks(engine: Engine, policy_folder: Path) -> None:
    results = ingest_folder(engine, FakeEmbedder(), policy_folder, origin="sample")

    assert statuses(results) == {"leave-policy": "created", "overtime-policy": "created"}
    assert counts(engine) == (2, sum(result.chunks for result in results))


def test_running_ingest_again_changes_and_embeds_nothing(
    engine: Engine, policy_folder: Path
) -> None:
    embedder = FakeEmbedder()
    ingest_folder(engine, embedder, policy_folder, origin="sample")
    before, embedded_before = counts(engine), len(embedder.embedded_texts)

    results = ingest_folder(engine, embedder, policy_folder, origin="sample")

    assert statuses(results) == {"leave-policy": "unchanged", "overtime-policy": "unchanged"}
    assert counts(engine) == before
    assert len(embedder.embedded_texts) == embedded_before


def test_edited_file_has_its_chunks_replaced_not_duplicated(
    engine: Engine, policy_folder: Path
) -> None:
    embedder = FakeEmbedder()
    first = statuses_and_chunks(ingest_folder(engine, embedder, policy_folder, origin="sample"))
    leave = policy_folder / "leave-policy.md"
    leave.write_text(leave.read_text() + "\n## 11. Extra Section\n\nA brand new clause.\n")

    results = ingest_folder(engine, embedder, policy_folder, origin="sample")

    assert statuses(results) == {"leave-policy": "updated", "overtime-policy": "unchanged"}
    assert statuses_and_chunks(results)["leave-policy"] == first["leave-policy"] + 1
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT c.chunk_index, c.content FROM chunks c JOIN documents d"
                " ON d.id = c.document_id WHERE d.slug = 'leave-policy' ORDER BY c.chunk_index"
            )
        ).all()
    assert [row.chunk_index for row in rows] == list(range(len(rows)))
    assert rows[-1].content == "A brand new clause."


def statuses_and_chunks(results) -> dict[str, int]:
    return {result.slug: result.chunks for result in results}


def test_changing_the_pipeline_version_re_embeds_everything(
    engine: Engine, policy_folder: Path
) -> None:
    ingest_folder(engine, FakeEmbedder(model_name="model-a"), policy_folder, origin="sample")
    model_b = FakeEmbedder(model_name="model-b")

    results = ingest_folder(engine, model_b, policy_folder, origin="sample")

    assert set(statuses(results).values()) == {"updated"}
    assert model_b.embedded_texts
    with engine.connect() as conn:
        versions = conn.execute(text("SELECT DISTINCT pipeline_version FROM documents")).scalars()
        assert [version.split("|")[0] for version in versions] == ["model-b"]


def test_every_chunk_keeps_its_document_identity_and_section(
    engine: Engine, policy_folder: Path
) -> None:
    ingest_folder(engine, FakeEmbedder(), policy_folder, origin="sample")

    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT d.slug, d.title, d.file_type, d.origin, c.section, c.section_path,"
                " c.word_count, vector_dims(c.embedding) AS dims"
                " FROM chunks c JOIN documents d ON d.id = c.document_id"
            )
        ).all()
    assert {(row.slug, row.title) for row in rows} == {
        ("leave-policy", "Leave Policy"),
        ("overtime-policy", "Overtime Policy"),
    }
    for row in rows:
        assert (row.file_type, row.origin, row.dims) == ("md", "sample", 384)
        assert row.section and row.section_path.endswith(row.section)
        assert row.word_count > 0


def test_embedded_text_includes_document_title_and_section_path(
    engine: Engine, policy_folder: Path
) -> None:
    embedder = FakeEmbedder()

    ingest_folder(engine, embedder, policy_folder, origin="sample")

    assert any(
        t.startswith("Leave Policy — 4. Annual Leave > 4.3 Carry Forward of Annual Leave\n")
        for t in embedder.embedded_texts
    )


def test_file_removed_from_the_folder_is_removed_from_the_database(
    engine: Engine, policy_folder: Path
) -> None:
    ingest_folder(engine, FakeEmbedder(), policy_folder, origin="sample")
    (policy_folder / "overtime-policy.md").unlink()

    results = ingest_folder(engine, FakeEmbedder(), policy_folder, origin="sample")

    assert statuses(results) == {"leave-policy": "unchanged", "overtime-policy": "removed"}
    with engine.connect() as conn:
        slugs = conn.execute(text("SELECT slug FROM documents")).scalars().all()
    assert slugs == ["leave-policy"]


def test_pdf_files_are_ingested(engine: Engine, tmp_path: Path) -> None:
    pdf = tmp_path / "leave-policy.pdf"
    shutil.copy(SAMPLE_POLICIES_DIR / "pdf" / "leave-policy.pdf", pdf)

    result = ingest_file(engine, FakeEmbedder(), pdf, origin="sample")

    assert (result.slug, result.status) == ("leave-policy", "created")
    with engine.connect() as conn:
        assert conn.execute(text("SELECT file_type FROM documents")).scalar_one() == "pdf"


def test_unsupported_file_type_is_rejected(engine: Engine, tmp_path: Path) -> None:
    notes = tmp_path / "notes.txt"
    notes.write_text("Not a policy")

    with pytest.raises(ValueError, match=r"only \.md and \.pdf"):
        ingest_file(engine, FakeEmbedder(), notes, origin="sample")


def test_embedding_model_with_the_wrong_dimension_is_rejected(
    engine: Engine, policy_folder: Path
) -> None:
    with pytest.raises(ValueError, match="384"):
        ingest_folder(engine, FakeEmbedder(dimension=10), policy_folder, origin="sample")
    assert counts(engine) == (0, 0)


def test_all_sample_policies_are_ingested(engine: Engine) -> None:
    results = ingest_folder(engine, FakeEmbedder(), SAMPLE_POLICIES_DIR, origin="sample")

    expected_chunks = {
        path.stem: len(chunk_document(parse_markdown(path.read_text(encoding="utf-8"))))
        for path in SAMPLE_POLICIES_DIR.glob("*.md")
    }
    assert statuses_and_chunks(results) == expected_chunks
    assert counts(engine) == (8, sum(expected_chunks.values()))


def test_command_line_ingests_the_sample_policies_twice_without_duplicates(
    engine: Engine,
    migrated_database_url: str,
    monkeypatch: pytest.MonkeyPatch,
    restore_root_logging: None,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("DATABASE_URL", migrated_database_url)
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path / "not-created-yet"))
    monkeypatch.setattr(ingest_cli, "build_embedder", lambda settings: FakeEmbedder())

    ingest_cli.main()
    after_first = counts(engine)
    ingest_cli.main()

    assert after_first[0] == 8
    assert counts(engine) == after_first


def test_command_line_also_ingests_uploaded_policies(
    engine: Engine,
    migrated_database_url: str,
    monkeypatch: pytest.MonkeyPatch,
    restore_root_logging: None,
    tmp_path: Path,
) -> None:
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    shutil.copy(UPLOAD_DEMO_POLICY, uploads)
    monkeypatch.setenv("DATABASE_URL", migrated_database_url)
    monkeypatch.setenv("UPLOAD_DIR", str(uploads))
    monkeypatch.setattr(ingest_cli, "build_embedder", lambda settings: FakeEmbedder())

    ingest_cli.main()

    with engine.connect() as conn:
        origins = dict(conn.execute(text("SELECT slug, origin FROM documents")).all())
    assert len(origins) == 9
    assert origins[UPLOAD_DEMO_POLICY.stem] == "upload"


def test_a_sample_with_the_same_bytes_as_an_upload_takes_it_over(
    engine: Engine, tmp_path: Path
) -> None:
    uploads, samples = tmp_path / "uploads", tmp_path / "samples"
    uploads.mkdir()
    samples.mkdir()
    shutil.copy(UPLOAD_DEMO_POLICY, uploads)
    ingest_folder(engine, FakeEmbedder(), uploads, origin="upload")
    shutil.copy(UPLOAD_DEMO_POLICY, samples)

    sample_results = ingest_folder(engine, FakeEmbedder(), samples, origin="sample")
    (uploads / UPLOAD_DEMO_POLICY.name).unlink()
    upload_results = ingest_folder(engine, FakeEmbedder(), uploads, origin="upload")

    assert statuses(sample_results) == {UPLOAD_DEMO_POLICY.stem: "updated"}
    assert upload_results == []  # nothing removed: the document now belongs to the sample
    with engine.connect() as conn:
        assert conn.execute(text("SELECT origin FROM documents")).scalars().all() == ["sample"]


def test_an_uploaded_file_with_a_sample_slug_is_skipped(
    engine: Engine, policy_folder: Path, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    ingest_folder(engine, FakeEmbedder(), policy_folder, origin="sample")
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    (uploads / "leave-policy.md").write_text("# Leave Policy\n\n## 1. Other\n\nOther text.\n")
    embedder = FakeEmbedder()

    results = ingest_folder(engine, embedder, uploads, origin="upload")

    assert statuses(results) == {"leave-policy": "skipped"}
    assert embedder.embedded_texts == []
    [record] = [r for r in caplog.records if getattr(r, "status", None) == "skipped"]
    assert record.levelname == "WARNING"
    assert record.slug == "leave-policy"
    with engine.connect() as conn:
        origin = conn.execute(text("SELECT origin FROM documents WHERE slug = 'leave-policy'"))
        assert origin.scalar_one() == "sample"


def test_a_new_sample_policy_takes_over_a_slug_used_by_an_upload(
    engine: Engine, policy_folder: Path, tmp_path: Path
) -> None:
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    (uploads / "leave-policy.md").write_text("# Leave Policy\n\n## 1. Old\n\nUploaded text.\n")
    ingest_folder(engine, FakeEmbedder(), uploads, origin="upload")

    sample_results = ingest_folder(engine, FakeEmbedder(), policy_folder, origin="sample")
    upload_results = ingest_folder(engine, FakeEmbedder(), uploads, origin="upload")

    assert statuses(sample_results)["leave-policy"] == "updated"
    assert statuses(upload_results) == {"leave-policy": "skipped"}
    with engine.connect() as conn:
        origin = conn.execute(text("SELECT origin FROM documents WHERE slug = 'leave-policy'"))
        assert origin.scalar_one() == "sample"


def test_each_document_is_logged_as_it_is_processed(
    engine: Engine, policy_folder: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level("INFO", logger="policypal.ingest")
    ingest_folder(engine, FakeEmbedder(), policy_folder, origin="sample")
    (policy_folder / "overtime-policy.md").unlink()

    ingest_folder(engine, FakeEmbedder(), policy_folder, origin="sample")

    logged = [(r.slug, r.status) for r in caplog.records if r.getMessage() == "ingest.document"]
    assert logged == [
        ("leave-policy", "created"),
        ("overtime-policy", "created"),
        ("leave-policy", "unchanged"),
        ("overtime-policy", "removed"),
    ]


NUL_POLICY = b"# Broken Policy\n\n## 1. Scope\n\nApplies to all\x00 staff.\n"


def test_a_file_that_fails_is_logged_and_skipped_and_the_rest_are_loaded(
    engine: Engine, policy_folder: Path, caplog: pytest.LogCaptureFixture
) -> None:
    (policy_folder / "broken-policy.md").write_bytes(NUL_POLICY)
    caplog.set_level("INFO", logger="policypal.ingest")

    results = ingest_folder(engine, FakeEmbedder(), policy_folder, origin="sample")

    assert statuses(results) == {
        "broken-policy": "failed",
        "leave-policy": "created",
        "overtime-policy": "created",
    }
    assert counts(engine)[0] == 2
    [record] = [r for r in caplog.records if r.getMessage() == "ingest.failed"]
    assert record.levelname == "ERROR"
    assert (record.slug, record.file, record.error) == (
        "broken-policy",
        "broken-policy.md",
        "ValueError",
    )
    assert "NUL character" in record.reason


def test_a_failed_file_keeps_its_last_good_version(engine: Engine, policy_folder: Path) -> None:
    ingest_folder(engine, FakeEmbedder(), policy_folder, origin="sample")
    before = counts(engine)
    (policy_folder / "overtime-policy.md").write_bytes(NUL_POLICY)

    results = ingest_folder(engine, FakeEmbedder(), policy_folder, origin="sample")

    assert statuses(results)["overtime-policy"] == "failed"
    assert counts(engine) == before  # not removed, not half-replaced


def test_an_unexpected_error_in_one_file_does_not_stop_the_others(
    engine: Engine, policy_folder: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Defence in depth: any error from one file (e.g. a parser bug) only skips that file."""
    real_parse = pipeline.parse_document

    def parse_or_crash(data: bytes, file_type: str):
        if data.startswith(b"# Overtime"):
            raise KeyError("a parser bug")
        return real_parse(data, file_type)  # type: ignore[arg-type]

    monkeypatch.setattr(pipeline, "parse_document", parse_or_crash)

    results = ingest_folder(engine, FakeEmbedder(), policy_folder, origin="sample")

    assert statuses(results) == {"leave-policy": "created", "overtime-policy": "failed"}


def test_a_database_outage_still_stops_ingestion(policy_folder: Path) -> None:
    """Without the database nothing can be loaded, so start-up must stop, not skip."""
    unreachable = make_engine("postgresql+psycopg://nobody:nothing@localhost:1/none")

    with pytest.raises(OperationalError):
        ingest_folder(unreachable, FakeEmbedder(), policy_folder, origin="sample")


def test_the_command_line_finishes_when_a_file_fails(
    engine: Engine,
    migrated_database_url: str,
    monkeypatch: pytest.MonkeyPatch,
    restore_root_logging: None,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The API container runs this before starting; a bad upload must not block start-up."""
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    (uploads / "broken-policy.md").write_bytes(NUL_POLICY)
    monkeypatch.setenv("DATABASE_URL", migrated_database_url)
    monkeypatch.setenv("UPLOAD_DIR", str(uploads))
    monkeypatch.setattr(ingest_cli, "build_embedder", lambda settings: FakeEmbedder())

    ingest_cli.main()

    assert counts(engine)[0] == 8
    # The command line logs JSON lines to stdout.
    lines = [json.loads(line) for line in capsys.readouterr().out.splitlines() if line]
    [summary] = [line for line in lines if line["message"] == "ingest.completed"]
    assert summary["documents_by_status"] == {"created": 8, "failed": 1}


def test_a_missing_folder_is_an_error_not_an_empty_folder(
    engine: Engine, policy_folder: Path, tmp_path: Path
) -> None:
    """Treating a missing folder as empty would remove every document from it."""
    ingest_folder(engine, FakeEmbedder(), policy_folder, origin="sample")

    with pytest.raises(FileNotFoundError):
        ingest_folder(engine, FakeEmbedder(), tmp_path / "missing", origin="sample")

    assert counts(engine)[0] == 2
