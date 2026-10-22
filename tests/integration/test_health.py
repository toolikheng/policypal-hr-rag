from fastapi.testclient import TestClient
from sqlalchemy import Engine

from policypal import __version__
from policypal.api.main import create_app
from policypal.ingest.pipeline import SAMPLE_POLICIES_DIR, ingest_folder
from tests.fakes import FakeEmbedder
from tests.helpers import make_settings


def test_health_is_ok_when_database_is_up_and_migrated(client: TestClient, engine: Engine) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "database": "ok",
        "documents": 0,
        "chunks": 0,
        "version": __version__,
    }


def test_health_reports_document_and_chunk_counts(client: TestClient, engine: Engine) -> None:
    results = ingest_folder(engine, FakeEmbedder(), SAMPLE_POLICIES_DIR, origin="sample")

    body = client.get("/health").json()

    assert body["documents"] == 8
    assert body["chunks"] == sum(result.chunks for result in results)


def test_health_is_503_when_database_is_unreachable() -> None:
    # Port 1 on localhost has nothing listening, so the connection is refused immediately.
    settings = make_settings("postgresql+psycopg://nobody:nothing@localhost:1/none")

    with TestClient(create_app(settings)) as unreachable_client:
        response = unreachable_client.get("/health")

    assert response.status_code == 503
    assert response.json() == {
        "status": "unavailable",
        "database": "unreachable",
        "documents": None,
        "chunks": None,
        "version": __version__,
    }


def test_every_response_has_a_request_id(client: TestClient) -> None:
    response = client.get("/health")

    assert len(response.headers["X-Request-ID"]) == 32


def test_valid_incoming_request_id_is_echoed(client: TestClient) -> None:
    response = client.get("/health", headers={"X-Request-ID": "trace-123"})

    assert response.headers["X-Request-ID"] == "trace-123"


def test_invalid_incoming_request_id_is_replaced(client: TestClient) -> None:
    response = client.get("/health", headers={"X-Request-ID": "bad id with spaces <script>"})

    assert response.headers["X-Request-ID"] != "bad id with spaces <script>"
    assert len(response.headers["X-Request-ID"]) == 32


def test_openapi_documents_health_responses(client: TestClient) -> None:
    health = client.get("/openapi.json").json()["paths"]["/health"]["get"]

    assert {"200", "503"} <= set(health["responses"])
