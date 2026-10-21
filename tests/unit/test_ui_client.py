import httpx
import pytest

from ui.api_client import ApiUnavailableError, PolicyPalClient


def client_returning(status_code: int, body: dict) -> PolicyPalClient:
    transport = httpx.MockTransport(lambda request: httpx.Response(status_code, json=body))
    return PolicyPalClient(httpx.Client(transport=transport, base_url="http://api"))


def test_health_returns_api_body_when_ok() -> None:
    body = {"status": "ok", "database": "ok", "version": "0.1.0"}

    assert client_returning(200, body).health() == body


def test_health_returns_api_body_when_api_reports_unavailable() -> None:
    body = {"status": "unavailable", "database": "unreachable", "version": "0.1.0"}

    assert client_returning(503, body).health() == body


def test_health_raises_clear_error_when_api_cannot_be_reached() -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    client = PolicyPalClient(
        httpx.Client(transport=httpx.MockTransport(refuse), base_url="http://api")
    )

    with pytest.raises(ApiUnavailableError, match="Cannot reach the PolicyPal API"):
        client.health()
