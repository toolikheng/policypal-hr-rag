from alembic import command
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from policypal.api.main import create_app
from tests.helpers import alembic_config, make_settings


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
        with TestClient(create_app(make_settings(migrated_database_url))) as client:
            response = client.get("/health")
        assert response.status_code == 503
        assert response.json()["database"] == "not_migrated"
    finally:
        command.upgrade(config, "head")

    assert vector_extension_installed(migrated_database_url)
