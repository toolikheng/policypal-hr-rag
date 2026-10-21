import httpx
import pytest

from ui.api_client import ApiError, PolicyPalClient


def client_with(handler) -> PolicyPalClient:
    return PolicyPalClient(
        httpx.Client(transport=httpx.MockTransport(handler), base_url="http://api")
    )


def client_returning(status_code: int, body: dict) -> PolicyPalClient:
    return client_with(lambda request: httpx.Response(status_code, json=body))


def test_health_returns_api_body_when_ok() -> None:
    body = {"status": "ok", "database": "ok", "version": "0.1.0"}

    assert client_returning(200, body).health() == body


def test_health_returns_api_body_when_api_reports_unavailable() -> None:
    body = {"status": "unavailable", "database": "unreachable", "version": "0.1.0"}

    assert client_returning(503, body).health() == body


def test_health_raises_clear_error_when_api_cannot_be_reached() -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    with pytest.raises(ApiError, match="Cannot reach the PolicyPal API"):
        client_with(refuse).health()


def test_health_raises_clear_error_on_unexpected_status() -> None:
    with pytest.raises(ApiError, match="HTTP 500"):
        client_returning(500, {"detail": "Internal Server Error"}).health()


def test_health_raises_clear_error_when_body_is_not_json() -> None:
    not_json = client_with(lambda request: httpx.Response(200, text="<html>proxy page</html>"))

    with pytest.raises(ApiError, match="not valid JSON"):
        not_json.health()
