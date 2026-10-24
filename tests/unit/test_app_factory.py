import logging

import pytest

from policypal.api.main import create_app, create_app_from_env
from policypal.logging_setup import JsonFormatter
from tests.helpers import NO_DATABASE, make_settings


def test_create_app_does_not_touch_global_logging(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO)

    create_app(make_settings(NO_DATABASE))
    logging.getLogger("policypal.test").warning("still captured")

    assert "still captured" in caplog.text


def test_create_app_from_env_reads_settings_and_sets_up_json_logging(
    monkeypatch: pytest.MonkeyPatch, restore_root_logging: None
) -> None:
    monkeypatch.setenv("DATABASE_URL", NO_DATABASE)

    app = create_app_from_env()

    assert app.title == "PolicyPal API"
    [handler] = logging.getLogger().handlers
    assert isinstance(handler.formatter, JsonFormatter)


def test_the_api_process_does_not_log_alembic_details_on_every_health_check(
    monkeypatch: pytest.MonkeyPatch, restore_root_logging: None
) -> None:
    # /health checks the database's migration on every call (every 10 s in Compose), and
    # alembic logs two INFO lines each time. Warnings and errors still get through.
    alembic_logger = logging.getLogger("alembic.runtime.migration")
    monkeypatch.setattr(alembic_logger, "level", alembic_logger.level)  # restored afterwards
    monkeypatch.setenv("DATABASE_URL", NO_DATABASE)

    create_app_from_env()

    assert alembic_logger.getEffectiveLevel() == logging.WARNING
