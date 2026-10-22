import pytest
from pydantic import ValidationError

from policypal.config import Settings

SETTING_ENV_VARS = ["DATABASE_URL", "LLM_PROVIDER", "LOG_LEVEL", "EMBEDDING_QUERY_INSTRUCTION"]


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in SETTING_ENV_VARS:
        monkeypatch.delenv(name, raising=False)


def test_database_url_is_required() -> None:
    with pytest.raises(ValidationError, match="database_url"):
        Settings(_env_file=None)


def test_other_settings_have_safe_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@db:5432/x")

    settings = Settings(_env_file=None)

    assert settings.llm_provider == "ollama"
    assert settings.log_level == "INFO"


def test_questions_use_the_bge_query_instruction_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@db:5432/x")

    settings = Settings(_env_file=None)

    # From the bge-small-en-v1.5 model card; note the trailing space.
    assert (
        settings.embedding_query_instruction
        == "Represent this sentence for searching relevant passages: "
    )


def test_query_instruction_can_be_turned_off(monkeypatch: pytest.MonkeyPatch) -> None:
    # The Phase 5 evaluation compares retrieval with and without the instruction.
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@db:5432/x")
    monkeypatch.setenv("EMBEDDING_QUERY_INSTRUCTION", "")

    assert Settings(_env_file=None).embedding_query_instruction == ""


def test_values_come_from_environment_variables(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@db:5432/x")
    monkeypatch.setenv("LLM_PROVIDER", "extractive")

    settings = Settings(_env_file=None)

    assert settings.database_url == "postgresql+psycopg://u:p@db:5432/x"
    assert settings.llm_provider == "extractive"


@pytest.mark.parametrize("provider", ["openai", "fake", ""])
def test_unknown_llm_provider_is_rejected(monkeypatch: pytest.MonkeyPatch, provider: str) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@db:5432/x")
    monkeypatch.setenv("LLM_PROVIDER", provider)

    with pytest.raises(ValidationError, match="llm_provider"):
        Settings(_env_file=None)


def test_invalid_log_level_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@db:5432/x")
    monkeypatch.setenv("LOG_LEVEL", "LOUD")

    with pytest.raises(ValidationError, match="log_level"):
        Settings(_env_file=None)
