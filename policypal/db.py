"""Database engine and health check."""

import logging
from functools import cache
from pathlib import Path
from typing import Literal

from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Engine, create_engine
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"

DatabaseStatus = Literal["ok", "unreachable", "not_migrated"]


def make_engine(database_url: str) -> Engine:
    # pool_pre_ping replaces dead connections (e.g. after a database restart);
    # connect_timeout keeps /health fast when the database is down.
    return create_engine(database_url, pool_pre_ping=True, connect_args={"connect_timeout": 3})


@cache
def latest_migration() -> str | None:
    """The newest migration revision in the code (read once; files don't change at runtime)."""
    return ScriptDirectory(str(MIGRATIONS_DIR)).get_current_head()


def check_database(engine: Engine) -> DatabaseStatus:
    """Report whether the database is reachable and its schema is at the newest migration."""
    try:
        with engine.connect() as conn:
            current = MigrationContext.configure(conn).get_current_revision()
    except SQLAlchemyError as exc:
        # Log the error type only: the full message can contain the connection string.
        logger.warning("database.unreachable", extra={"error": type(exc).__name__})
        return "unreachable"
    return "ok" if current == latest_migration() else "not_migrated"
