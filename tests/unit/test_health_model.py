import pytest

from policypal.api.schemas import HealthResponse, LLMHealth


@pytest.mark.parametrize(
    ("database", "llm_status", "expected_status"),
    [
        ("ok", "ok", "ok"),
        ("ok", "unavailable", "degraded"),
        ("ok", "model_missing", "degraded"),
        ("unreachable", "ok", "unavailable"),
        ("not_migrated", "unavailable", "unavailable"),
    ],
)
def test_status_is_derived_from_the_checks(
    database: str, llm_status: str, expected_status: str
) -> None:
    report = HealthResponse(
        database=database,
        llm=LLMHealth(provider="ollama", model="llama3.2:3b", status=llm_status),
        documents=None,
        chunks=None,
        files_not_loaded=None,
        version="0.1.0",
    )

    assert report.status == expected_status
    assert report.model_dump()["status"] == expected_status
