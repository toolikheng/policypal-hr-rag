import pytest
from pydantic import ValidationError

from policypal.config import Settings

SETTING_ENV_VARS = [
    "DATABASE_URL",
    "LLM_PROVIDER",
    "LOG_LEVEL",
    "EMBEDDING_QUERY_INSTRUCTION",
    "RETRIEVAL_TOP_K",
    "OLLAMA_BASE_URL",
    "OLLAMA_MODEL",
    "OLLAMA_TIMEOUT_SECONDS",
    "MIN_SIMILARITY",
]


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


def test_retrieval_returns_five_chunks_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@db:5432/x")

    assert Settings(_env_file=None).retrieval_top_k == 5


@pytest.mark.parametrize("top_k", ["0", "21", "five"])
def test_invalid_retrieval_top_k_is_rejected(monkeypatch: pytest.MonkeyPatch, top_k: str) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@db:5432/x")
    monkeypatch.setenv("RETRIEVAL_TOP_K", top_k)

    with pytest.raises(ValidationError, match="retrieval_top_k"):
        Settings(_env_file=None)


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


def test_ollama_settings_have_local_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@db:5432/x")

    settings = Settings(_env_file=None)

    assert settings.ollama_base_url == "http://localhost:11434"
    assert settings.ollama_model == "llama3.2:3b"
    assert settings.ollama_timeout_seconds == 60


@pytest.mark.parametrize("timeout", ["0", "-5", "601"])
def test_invalid_ollama_timeout_is_rejected(monkeypatch: pytest.MonkeyPatch, timeout: str) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@db:5432/x")
    monkeypatch.setenv("OLLAMA_TIMEOUT_SECONDS", timeout)

    with pytest.raises(ValidationError, match="ollama_timeout_seconds"):
        Settings(_env_file=None)


def test_min_similarity_has_the_provisional_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@db:5432/x")

    # Provisional (Phase 2), set from hand-picked questions; calibrated in Phase 5.
    assert Settings(_env_file=None).min_similarity == 0.65


@pytest.mark.parametrize("value", ["-0.1", "1.5", "high"])
def test_invalid_min_similarity_is_rejected(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@db:5432/x")
    monkeypatch.setenv("MIN_SIMILARITY", value)

    with pytest.raises(ValidationError, match="min_similarity"):
        Settings(_env_file=None)
