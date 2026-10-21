"""Alembic environment: runs migrations against the configured database."""

from alembic import context
from sqlalchemy import create_engine

from policypal.config import Settings
from policypal.logging_setup import configure_logging

config = context.config

if config.cmd_opts is not None:
    # Run from the `alembic` command line: use the app's settings and its JSON logging.
    settings = Settings()
    configure_logging(settings.log_level)
    database_url = settings.database_url
else:
    # Called from Python (the test suite), which passes the URL and owns logging.
    database_url = config.attributes["database_url"]

engine = create_engine(database_url)
with engine.connect() as connection:
    context.configure(connection=connection)
    with context.begin_transaction():
        context.run_migrations()
engine.dispose()
