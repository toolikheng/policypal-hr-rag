"""Shared test fixtures.

Database tests run against a real PostgreSQL + pgvector database (TEST_DATABASE_URL).
Locally they are skipped with a clear reason if the database isn't running
(start it with `make db-up`). CI sets REQUIRE_DB=1 so a missing database fails instead.
"""

import logging
import os
from collections.abc import Iterator

import pytest
from alembic import command
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import OperationalError

from policypal.config import Settings
from policypal.db import make_engine
from tests.helpers import alembic_config, build_test_app

DEFAULT_TEST_DATABASE_URL = (
    "postgresql+psycopg://policypal:policypal-local-dev@localhost:5433/policypal_test"
)


@pytest.fixture(autouse=True)
def no_settings_from_the_shell(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove every PolicyPal setting from the environment, so a variable exported in the
    developer's shell (ADMIN_TOKEN, LLM_PROVIDER, ...) can't change a test's result. The
    names come from Settings itself, so a new setting is covered without a list to update.
    Tests that need a variable set it with monkeypatch.setenv."""
    for name in Settings.model_fields:
        monkeypatch.delenv(name.upper(), raising=False)


@pytest.fixture(scope="session")
def test_database_url() -> str:
    url = os.environ.get("TEST_DATABASE_URL", DEFAULT_TEST_DATABASE_URL)
    engine = create_engine(url, connect_args={"connect_timeout": 3})
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except OperationalError:
        # render_as_string() hides the password by default.
        where = engine.url.render_as_string()
        message = f"Test database not reachable ({where}). Run `make db-up`."
        if os.environ.get("REQUIRE_DB") == "1":
            pytest.fail(message)
        pytest.skip(message)
    finally:
        engine.dispose()
    return url


@pytest.fixture(scope="session")
def migrated_database_url(test_database_url: str) -> str:
    command.upgrade(alembic_config(test_database_url), "head")
    return test_database_url


@pytest.fixture
def client(migrated_database_url: str) -> Iterator[TestClient]:
    with TestClient(build_test_app(migrated_database_url)) as test_client:
        yield test_client


@pytest.fixture
def engine(migrated_database_url: str) -> Iterator[Engine]:
    """An engine on an empty, migrated test database (tables are emptied before each test)."""
    engine = make_engine(migrated_database_url)
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE documents, conversations RESTART IDENTITY CASCADE"))
    yield engine
    engine.dispose()


@pytest.fixture
def restore_root_logging() -> Iterator[None]:
    """For tests that call configure_logging(), which changes global logging state."""
    root = logging.getLogger()
    handlers, level = list(root.handlers), root.level
    yield
    root.handlers, root.level = handlers, level
