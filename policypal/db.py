"""Database engine and health check."""

import logging
from typing import Literal

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)

DatabaseStatus = Literal["ok", "unreachable", "not_migrated"]


def make_engine(database_url: str) -> Engine:
    # pool_pre_ping replaces dead connections (e.g. after a database restart);
    # connect_timeout keeps /health fast when the database is down.
    return create_engine(database_url, pool_pre_ping=True, connect_args={"connect_timeout": 3})


def check_database(engine: Engine) -> DatabaseStatus:
    """Report whether the database is reachable and migrated (pgvector installed)."""
    try:
        with engine.connect() as conn:
            row = conn.execute(text("SELECT 1 FROM pg_extension WHERE extname = 'vector'")).first()
    except SQLAlchemyError as exc:
        # Log the error type only: the full message can contain the connection string.
        logger.warning("database.unreachable", extra={"error": type(exc).__name__})
        return "unreachable"
    return "ok" if row is not None else "not_migrated"
