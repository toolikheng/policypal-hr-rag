import pytest

from policypal.api.schemas import HealthResponse


@pytest.mark.parametrize(
    ("database", "expected_status"),
    [("ok", "ok"), ("unreachable", "unavailable"), ("not_migrated", "unavailable")],
)
def test_status_is_derived_from_the_database_check(database: str, expected_status: str) -> None:
    report = HealthResponse(database=database, documents=None, chunks=None, version="0.1.0")

    assert report.status == expected_status
    assert report.model_dump()["status"] == expected_status
