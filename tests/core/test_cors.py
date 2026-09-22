"""CORS: which websites may call the API from a browser (D-044).

A browser sends a *preflight* (OPTIONS with Access-Control-Request-Method)
before any request a page could not have made with a plain form, and only
goes ahead if we answer yes. These tests speak to the middleware the way a
browser would.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core import cors
from app.core.config import settings
from app.core.cors import (
    ALLOWED_METHODS,
    ALLOWED_REQUEST_HEADERS,
    EXPOSED_RESPONSE_HEADERS,
    PREFLIGHT_CACHE_SECONDS,
)
from app.main import app as real_app

DASHBOARD = "https://app.example.in"
STRANGER = "https://evil.example.com"


@pytest.fixture
def calls() -> dict[str, int]:
    """Counts how often a route ran, to prove when it never did."""
    return {"count": 0}


def build_client(calls: dict[str, int]) -> TestClient:
    app = FastAPI()
    cors.install(app)

    @app.get("/thing")
    def read_thing() -> dict[str, str]:
        calls["count"] += 1
        return {"status": "ok"}

    @app.post("/thing")
    def create_thing() -> dict[str, str]:
        calls["count"] += 1
        return {"status": "created"}

    return TestClient(app)


@pytest.fixture
def client(monkeypatch, calls) -> TestClient:
    monkeypatch.setattr(settings, "cors_allowed_origins", DASHBOARD)
    return build_client(calls)


def preflight(
    client: TestClient, origin: str, method: str = "POST", headers: str | None = None
):
    request_headers = {"Origin": origin, "Access-Control-Request-Method": method}
    if headers is not None:
        request_headers["Access-Control-Request-Headers"] = headers
    return client.options("/thing", headers=request_headers)


# --- Preflight ------------------------------------------------------------


def test_the_dashboard_may_send_a_signed_in_retry_safe_write(client, calls):
    response = preflight(
        client, DASHBOARD, headers="Authorization, Content-Type, Idempotency-Key"
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == DASHBOARD
    assert set(response.headers["access-control-allow-methods"].split(", ")) == set(
        ALLOWED_METHODS
    )
    assert response.headers["access-control-max-age"] == str(PREFLIGHT_CACHE_SECONDS)
    # Answered by the CORS layer: the route itself never ran.
    assert calls["count"] == 0


@pytest.mark.parametrize("header", ALLOWED_REQUEST_HEADERS)
def test_every_header_the_api_reads_may_be_sent(client, header):
    assert preflight(client, DASHBOARD, headers=header).status_code == 200


def test_an_unlisted_website_is_refused(client):
    response = preflight(client, STRANGER)

    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers


def test_a_look_alike_of_the_dashboard_is_refused(client):
    """Exact match only: no prefix, suffix or subdomain tricks."""
    for origin in (
        "https://app.example.in.evil.com",
        "https://evil-app.example.in",
        "http://app.example.in",
    ):
        assert preflight(client, origin).status_code == 400, origin


def test_a_method_the_api_does_not_use_is_refused(client):
    assert preflight(client, DASHBOARD, method="DELETE").status_code == 400


def test_a_header_the_api_does_not_read_is_refused(client):
    response = preflight(client, DASHBOARD, headers="Authorization, X-Admin")

    assert response.status_code == 400


def test_no_website_may_call_while_the_list_is_empty(monkeypatch, calls):
    monkeypatch.setattr(settings, "cors_allowed_origins", "")
    client = build_client(calls)

    for origin in (DASHBOARD, STRANGER, "http://localhost:5173"):
        assert preflight(client, origin).status_code == 400, origin


# --- Actual requests ---------------------------------------------------------


def test_the_dashboard_can_read_the_answer_and_our_headers(client):
    response = client.get("/thing", headers={"Origin": DASHBOARD})

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == DASHBOARD
    exposed = response.headers["access-control-expose-headers"].split(", ")
    assert set(exposed) == set(EXPOSED_RESPONSE_HEADERS)
    # Caches must keep one copy per website, never hand one site's answer to another.
    assert "Origin" in response.headers["vary"]


def test_a_stranger_gets_no_permission_to_read(client):
    """The request still runs (a browser sends simple requests without asking
    first), but the answer carries no permission, so the browser hides it
    from the stranger's page."""
    response = client.get("/thing", headers={"Origin": STRANGER})

    assert "access-control-allow-origin" not in response.headers


def test_cookies_are_never_allowed_across_sites(client):
    for response in (
        preflight(client, DASHBOARD),
        client.get("/thing", headers={"Origin": DASHBOARD}),
    ):
        assert "access-control-allow-credentials" not in response.headers


def test_the_answer_never_allows_every_website(client):
    for origin in (DASHBOARD, STRANGER):
        response = client.get("/thing", headers={"Origin": origin})
        assert response.headers.get("access-control-allow-origin") != "*"


def test_the_mobile_app_is_unaffected(client, calls):
    """A native app sends no Origin, so CORS never applies to it."""
    response = client.get("/thing")

    assert response.status_code == 200
    assert calls["count"] == 1
    assert not [name for name in response.headers if name.startswith("access-control")]


# --- The lists match the real API ------------------------------------------


def real_operations():
    for item in real_app.openapi()["paths"].values():
        yield from item.items()


def test_every_method_the_api_uses_is_allowed():
    """A new DELETE or PUT endpoint fails here until the dashboard may call it."""
    used = {method.upper() for method, _ in real_operations()}

    assert used <= set(ALLOWED_METHODS)


def test_every_header_the_contract_documents_is_allowed():
    allowed = {header.lower() for header in ALLOWED_REQUEST_HEADERS}
    documented = {
        parameter["name"].lower()
        for _, operation in real_operations()
        for parameter in operation.get("parameters", [])
        if parameter["in"] == "header"
    }

    assert documented
    assert documented <= allowed


def test_the_sign_in_header_is_allowed():
    schemes = real_app.openapi()["components"]["securitySchemes"]

    assert {scheme["scheme"] for scheme in schemes.values()} == {"bearer"}
    assert "Authorization" in ALLOWED_REQUEST_HEADERS
