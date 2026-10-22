import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from alembic import command
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

from tests.helpers import alembic_config, build_test_app


def vector_extension_installed(database_url: str) -> bool:
    engine = create_engine(database_url)
    try:
        with engine.connect() as conn:
            row = conn.execute(text("SELECT 1 FROM pg_extension WHERE extname = 'vector'")).first()
    finally:
        engine.dispose()
    return row is not None


def test_upgrade_head_installs_vector_extension(migrated_database_url: str) -> None:
    assert vector_extension_installed(migrated_database_url)


def test_downgrade_then_upgrade_round_trip(migrated_database_url: str) -> None:
    config = alembic_config(migrated_database_url)
    try:
        command.downgrade(config, "base")
        assert not vector_extension_installed(migrated_database_url)

        # While the schema is missing, /health must say so instead of claiming "ok".
        with TestClient(build_test_app(migrated_database_url)) as client:
            response = client.get("/health")
        assert response.status_code == 503
        assert response.json()["database"] == "not_migrated"
    finally:
        command.upgrade(config, "head")

    assert vector_extension_installed(migrated_database_url)


def test_health_is_not_migrated_when_database_is_behind_the_code(
    migrated_database_url: str,
) -> None:
    """Being reachable isn't enough: the schema must be at the newest migration."""
    engine = create_engine(migrated_database_url)
    try:
        with engine.begin() as conn:
            head = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            conn.execute(text("UPDATE alembic_version SET version_num = 'older'"))
        with TestClient(build_test_app(migrated_database_url)) as client:
            response = client.get("/health")
    finally:
        with engine.begin() as conn:
            conn.execute(text("UPDATE alembic_version SET version_num = :head"), {"head": head})
        engine.dispose()

    assert response.status_code == 503
    assert response.json()["database"] == "not_migrated"


def test_alembic_command_line_works_locally_and_logs_json(migrated_database_url: str) -> None:
    """`alembic upgrade head` from the repo root (no PYTHONPATH) logs JSON lines."""
    alembic_cli = Path(sys.executable).parent / "alembic"
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    env |= {"DATABASE_URL": migrated_database_url, "LOG_LEVEL": "INFO"}

    result = subprocess.run(
        [str(alembic_cli), "upgrade", "head"], env=env, capture_output=True, text=True, timeout=60
    )

    assert result.returncode == 0, result.stderr
    lines = [line for line in (result.stdout + result.stderr).splitlines() if line.strip()]
    assert lines, "expected alembic to log something"
    for line in lines:
        json.loads(line)  # raises if any line is not JSON


def test_documents_and_chunks_tables_have_vector_index_and_checks(engine) -> None:
    with engine.connect() as conn:
        index = conn.execute(
            text("SELECT indexdef FROM pg_indexes WHERE indexname = 'chunks_embedding_hnsw_idx'")
        ).scalar_one()
    assert "USING hnsw (embedding vector_cosine_ops)" in index

    with pytest.raises(IntegrityError), engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO documents (slug, title, source_filename, file_type, origin,"
                " content_sha256, pipeline_version) VALUES"
                " ('x', 'X', 'x.txt', 'txt', 'sample', repeat('0', 64), 'v')"
            )
        )
