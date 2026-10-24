"""Browsers may call the API from another site only if that site is in CORS_ORIGINS.

The widget is served by the API itself (same origin), so it needs no CORS. CORS is for
embedding the widget in a page on another site.
"""

from fastapi.testclient import TestClient

from tests.helpers import NO_DATABASE, build_test_app

ALLOWED = "http://localhost:8080"
OTHER = "https://elsewhere.example"


def make_client(**settings: object) -> TestClient:
    return TestClient(build_test_app(NO_DATABASE, **settings))


def preflight(client: TestClient, origin: str, headers: str = "content-type"):
    """What a browser sends before a cross-site POST /ask with a JSON body."""
    return client.options(
        "/ask",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": headers,
        },
    )


def test_an_allowed_site_may_post_questions() -> None:
    with make_client(cors_origins=[ALLOWED]) as client:
        response = preflight(client, ALLOWED)

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == ALLOWED
    assert "POST" in response.headers["access-control-allow-methods"]


def test_a_site_not_on_the_list_gets_no_cors_header() -> None:
    with make_client(cors_origins=[ALLOWED]) as client:
        response = client.get("/openapi.json", headers={"Origin": OTHER})

    assert "access-control-allow-origin" not in response.headers


def test_by_default_no_site_gets_a_cors_header() -> None:
    with make_client() as client:
        response = preflight(client, ALLOWED)

    assert "access-control-allow-origin" not in response.headers


def test_the_admin_token_header_is_never_allowed_cross_site() -> None:
    # Admin requests come from the Streamlit UI (server side) or curl, never a browser page.
    with make_client(cors_origins=[ALLOWED]) as client:
        response = preflight(client, ALLOWED, headers="content-type,x-admin-token")

    assert response.status_code == 400


def test_the_request_id_header_is_readable_cross_site() -> None:
    with make_client(cors_origins=[ALLOWED]) as client:
        response = client.get("/openapi.json", headers={"Origin": ALLOWED})

    assert response.headers["access-control-allow-origin"] == ALLOWED
    assert "x-request-id" in response.headers["access-control-expose-headers"].lower()


def test_an_unexpected_error_still_reaches_an_allowed_site_with_its_request_id() -> None:
    # CORS is the outermost middleware, so it also adds its header to the 500 reply built by
    # the request-ID middleware. Otherwise the browser would hide the reply from the widget.
    app = build_test_app(NO_DATABASE, cors_origins=[ALLOWED])

    @app.get("/boom")
    def boom() -> None:
        raise RuntimeError("secret internal detail")

    with TestClient(app) as client:
        response = client.get("/boom", headers={"Origin": ALLOWED, "X-Request-ID": "trace-500"})

    assert response.status_code == 500
    assert response.json()["request_id"] == "trace-500"
    assert response.headers["access-control-allow-origin"] == ALLOWED


def test_cors_does_not_change_same_site_requests() -> None:
    with make_client(cors_origins=[ALLOWED]) as client:
        response = client.get("/openapi.json")

    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers
