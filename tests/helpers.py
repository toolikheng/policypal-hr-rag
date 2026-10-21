"""Small helpers shared by tests (fixtures live in conftest.py)."""

from alembic.config import Config

from policypal.config import Settings


def alembic_config(database_url: str) -> Config:
    config = Config("alembic.ini")
    config.attributes["database_url"] = database_url
    return config


def make_settings(database_url: str) -> Settings:
    # _env_file=None: tests must not depend on a developer's local .env file.
    return Settings(_env_file=None, database_url=database_url)
