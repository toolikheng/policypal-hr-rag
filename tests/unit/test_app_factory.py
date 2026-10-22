import logging

import pytest

from policypal.api.main import create_app, create_app_from_env
from policypal.logging_setup import JsonFormatter
from tests.helpers import make_settings


def test_create_app_does_not_touch_global_logging(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO)

    create_app(make_settings("postgresql+psycopg://user:pw@localhost:1/db"))
    logging.getLogger("policypal.test").warning("still captured")

    assert "still captured" in caplog.text


def test_create_app_from_env_reads_settings_and_sets_up_json_logging(
    monkeypatch: pytest.MonkeyPatch, restore_root_logging: None
) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://user:pw@localhost:1/db")

    app = create_app_from_env()

    assert app.title == "PolicyPal API"
    [handler] = logging.getLogger().handlers
    assert isinstance(handler.formatter, JsonFormatter)
