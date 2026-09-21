"""An unexpected error still gets every header our other answers get (D-045)."""

import logging
from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from fastapi.testclient import TestClient
from starlette.types import ASGIApp, Receive, Scope, Send

from app.core.errors import register_error_handlers
from app.core.request_id import RequestIdMiddleware
from app.core.security_headers import API_CSP, SecurityHeadersMiddleware
from app.core.unexpected_error import UnexpectedErrorMiddleware

SECRET_TEXT = "SELECT * FROM account WHERE phone = '+919876543210'"


class FailsOnOnePath:
    """Stands in for a middleware that breaks, like the rate limiter when
    Redis is down."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("path") == "/middleware-fails":
            raise ConnectionError(SECRET_TEXT)
        await self.app(scope, receive, send)


def make_app(*, with_layer: bool = True) -> FastAPI:
    app = FastAPI()
    register_error_handlers(app)
    # The same order as app/main.py: this layer inside the request ID and
    # the security headers, and outside the middleware it protects.
    app.add_middleware(FailsOnOnePath)
    if with_layer:
        app.add_middleware(UnexpectedErrorMiddleware)
    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)

    @app.get("/ok")
    def ok() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/crash")
    def crash() -> None:
        raise RuntimeError(SECRET_TEXT)

    @app.get("/breaks-mid-answer")
    def breaks_mid_answer() -> StreamingResponse:
        def chunks() -> Iterator[bytes]:
            yield b"first part"
            raise RuntimeError(SECRET_TEXT)

        return StreamingResponse(chunks())

    return app


@pytest.fixture
def client() -> TestClient:
    return TestClient(make_app(), raise_server_exceptions=False)


def assert_every_header(response) -> None:
    assert response.headers["content-security-policy"] == API_CSP
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["x-request-id"]


def test_without_this_layer_a_500_misses_the_security_headers():
    """The gap this layer closes, kept visible: Starlette answers from
    outside every middleware we add."""
    client = TestClient(make_app(with_layer=False), raise_server_exceptions=False)

    response = client.get("/crash")

    assert response.status_code == 500
    assert "content-security-policy" not in response.headers


def test_an_unexpected_error_gets_every_header(client):
    response = client.get("/crash")

    assert response.status_code == 500
    assert_every_header(response)


def test_the_answer_is_our_usual_500_and_reveals_nothing(client):
    response = client.get("/crash", headers={"X-Request-ID": "trace-500"})

    assert response.headers["content-type"] == "application/problem+json"
    body = response.json()
    assert body["code"] == "internal_error"
    assert body["title"] == "Something went wrong on our side. Please try again"
    assert body["request_id"] == "trace-500"
    assert response.headers["x-request-id"] == "trace-500"
    assert "+919876543210" not in response.text
    assert "SELECT" not in response.text


def test_the_error_is_logged_with_its_request_id(client, caplog):
    with caplog.at_level(logging.ERROR):
        client.get("/crash", headers={"X-Request-ID": "trace-log"})

    logged = [r for r in caplog.records if "trace-log" in r.getMessage()]
    assert len(logged) == 1
    assert logged[0].exc_info is not None


def test_a_failure_inside_another_middleware_is_caught_too(client):
    response = client.get("/middleware-fails")

    assert response.status_code == 500
    assert response.json()["code"] == "internal_error"
    assert_every_header(response)


def test_an_error_after_the_answer_started_is_passed_on():
    """Half an answer has gone out; a 500 cannot replace it now."""
    client = TestClient(make_app(), raise_server_exceptions=True)

    # The original error, not a new one from trying to answer twice.
    with pytest.raises(RuntimeError, match=r"^SELECT"):
        client.get("/breaks-mid-answer")


def test_a_normal_answer_is_untouched(client):
    response = client.get("/ok")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert_every_header(response)


def test_startup_and_shutdown_pass_through():
    with TestClient(make_app()) as client:
        assert client.get("/ok").status_code == 200
