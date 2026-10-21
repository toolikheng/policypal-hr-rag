"""Alembic environment: runs migrations against the configured database."""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine

from policypal.config import get_settings

config = context.config

# Only configure logging when run from the `alembic` command line; inside the app or
# the test suite we keep their logging setup.
if config.config_file_name is not None and not config.attributes.get("database_url"):
    fileConfig(config.config_file_name)

# Tests pass the URL in directly; everything else uses the DATABASE_URL setting.
database_url = config.attributes.get("database_url") or get_settings().database_url

engine = create_engine(database_url)
with engine.connect() as connection:
    context.configure(connection=connection)
    with context.begin_transaction():
        context.run_migrations()
engine.dispose()
