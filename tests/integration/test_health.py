import httpx
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from policypal import __version__
from policypal.ingest.pipeline import SAMPLE_POLICIES_DIR, ingest_folder
from policypal.llm.ollama import OllamaProvider
from tests.fakes import FakeEmbedder, FakeLLM
from tests.helpers import build_test_app

FAKE_LLM_OK = {"provider": "fake", "model": "fake-model", "status": "ok"}


def test_health_is_ok_when_database_is_up_and_migrated(client: TestClient, engine: Engine) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "database": "ok",
        "llm": FAKE_LLM_OK,
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
    app = build_test_app("postgresql+psycopg://nobody:nothing@localhost:1/none")

    with TestClient(app) as unreachable_client:
        response = unreachable_client.get("/health")

    assert response.status_code == 503
    assert response.json() == {
        "status": "unavailable",
        "database": "unreachable",
        "llm": FAKE_LLM_OK,
        "documents": None,
        "chunks": None,
        "version": __version__,
    }


def test_health_is_degraded_but_200_when_the_llm_is_unavailable(
    migrated_database_url: str, engine: Engine
) -> None:
    # Questions are still answered (with quoted policy text), so the API stays up.
    app = build_test_app(migrated_database_url, llm=FakeLLM(status="unavailable"))

    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "degraded"
    assert body["llm"] == {"provider": "fake", "model": "fake-model", "status": "unavailable"}


def test_health_reports_an_ollama_model_that_is_not_downloaded(
    migrated_database_url: str, engine: Engine
) -> None:
    def tags(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"models": [{"name": "llama3.2:1b"}]})

    ollama = OllamaProvider(
        "http://ollama:11434", "llama3.2:3b", 60, transport=httpx.MockTransport(tags)
    )

    with TestClient(build_test_app(migrated_database_url, llm=ollama)) as client:
        body = client.get("/health").json()

    assert body["status"] == "degraded"
    assert body["llm"] == {"provider": "ollama", "model": "llama3.2:3b", "status": "model_missing"}


def test_extractive_mode_is_healthy_without_an_llm(
    migrated_database_url: str, engine: Engine
) -> None:
    app = build_test_app(migrated_database_url, llm_provider="extractive")

    with TestClient(app) as client:
        body = client.get("/health").json()

    assert body["status"] == "ok"
    assert body["llm"] == {"provider": "extractive", "model": None, "status": "ok"}


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
