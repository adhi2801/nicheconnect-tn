"""The request body cap: how much a caller may send before we refuse."""

import asyncio
from collections.abc import Iterator

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app.core.body_limit import (
    MAX_BODY_BYTES,
    BodyLimitMiddleware,
    RequestBodyTooLarge,
    declared_length,
)
from app.core.errors import register_error_handlers
from app.core.request_id import RequestIdMiddleware

# Small on purpose: the rule is the same at 100 bytes as at a megabyte, and
# the tests stay fast.
LIMIT = 100


@pytest.fixture
def calls() -> dict[str, int]:
    """Counts how often the route ran, to prove when it never did."""
    return {"count": 0}


@pytest.fixture
def client(calls) -> TestClient:
    app = FastAPI()
    register_error_handlers(app)
    app.add_middleware(BodyLimitMiddleware, max_bytes=LIMIT)
    app.add_middleware(RequestIdMiddleware)

    @app.post("/echo")
    async def echo(request: Request) -> dict[str, int]:
        calls["count"] += 1
        body = await request.body()
        return {"bytes": len(body)}

    @app.get("/nothing")
    async def nothing() -> dict[str, str]:
        calls["count"] += 1
        return {"status": "ok"}

    return TestClient(app)


def stream(total: int, chunk: int = 32) -> Iterator[bytes]:
    """Yield `total` bytes in pieces, so httpx sends them chunked.

    A chunked body carries no Content-Length, which is the case the declared
    size cannot catch.
    """
    sent = 0
    while sent < total:
        step = min(chunk, total - sent)
        yield b"x" * step
        sent += step


def assert_too_large(response) -> dict:
    assert response.status_code == 413, response.text
    assert response.headers["content-type"] == "application/problem+json"
    body = response.json()
    assert body["code"] == "body_too_large"
    return body


# --- what gets through ----------------------------------------------------


def test_an_ordinary_body_is_passed_straight_through(client, calls):
    response = client.post("/echo", content=b"x" * 50)

    assert response.status_code == 200
    assert response.json() == {"bytes": 50}
    assert calls["count"] == 1


def test_a_body_exactly_at_the_limit_is_allowed(client):
    """The limit is the largest body we accept, not the smallest we refuse."""
    response = client.post("/echo", content=b"x" * LIMIT)

    assert response.status_code == 200
    assert response.json() == {"bytes": LIMIT}


def test_a_request_with_no_body_is_unaffected(client):
    assert client.get("/nothing").status_code == 200


# --- the declared size ----------------------------------------------------


def test_a_body_over_the_limit_is_refused(client):
    response = client.post("/echo", content=b"x" * (LIMIT + 1))

    assert_too_large(response)


def test_an_oversized_body_never_reaches_the_route(client, calls):
    """The point of the header check: refuse before reading or routing."""
    client.post("/echo", content=b"x" * (LIMIT * 100))

    assert calls["count"] == 0


def test_the_refusal_says_what_the_limit_is(client):
    body = assert_too_large(client.post("/echo", content=b"x" * (LIMIT + 1)))

    assert body["detail"] == "Requests are limited to 100 bytes."
    assert body["title"] == "That request is too large"
    assert body["status"] == 413
    assert body["type"] == "https://nicheconnect.in/errors/body-too-large"


def test_the_refusal_carries_the_request_id(client):
    response = client.post("/echo", content=b"x" * (LIMIT + 1))

    assert response.headers["x-request-id"]
    assert response.json()["request_id"] == response.headers["x-request-id"]


# --- the real size --------------------------------------------------------


def test_a_chunked_body_over_the_limit_is_refused(client):
    """No Content-Length at all, so only the running count can catch it."""
    response = client.post("/echo", content=stream(LIMIT * 4))

    assert_too_large(response)


def test_a_chunked_body_under_the_limit_still_works(client):
    response = client.post("/echo", content=stream(LIMIT - 1))

    assert response.status_code == 200
    assert response.json() == {"bytes": LIMIT - 1}


def test_both_refusals_look_identical(client):
    """A caller cannot tell which check stopped them, and shouldn't need to."""
    declared = client.post("/echo", content=b"x" * (LIMIT + 1)).json()
    counted = client.post("/echo", content=stream(LIMIT * 4)).json()

    declared.pop("request_id")
    counted.pop("request_id")
    assert declared == counted


def test_a_lying_content_length_does_not_get_past_the_counter():
    """A hostile client declares 10 bytes and sends 800. The count decides.

    Driven at the ASGI level, because an HTTP client library corrects the
    header for you — which is exactly what an attacker would not do.
    """
    chunks = [
        {"type": "http.request", "body": b"x" * 400, "more_body": True},
        {"type": "http.request", "body": b"x" * 400, "more_body": False},
    ]

    async def app(scope, receive, send):
        while True:
            message = await receive()
            if not message.get("more_body"):
                return

    async def receive():
        return chunks.pop(0)

    async def send(message):
        raise AssertionError("no response should be sent")

    middleware = BodyLimitMiddleware(app, max_bytes=LIMIT * 5)
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/echo",
        "headers": [(b"content-length", b"10")],
        "state": {},
    }

    with pytest.raises(RequestBodyTooLarge):
        asyncio.run(middleware(scope, receive, send))


# --- reading the declared size -------------------------------------------


@pytest.mark.parametrize(
    ("headers", "expected"),
    [
        ([(b"content-length", b"42")], 42),
        ([(b"content-length", b"0")], 0),
        ([], None),
        ([(b"content-length", b"not-a-number")], None),
        ([(b"content-length", b"")], None),
        ([(b"content-type", b"application/json")], None),
    ],
)
def test_the_declared_length_is_read_or_ignored(headers, expected):
    """A header that isn't a plain number tells us nothing, so it's ignored
    and the real byte count decides instead."""
    assert declared_length({"headers": headers}) == expected


# --- the default ----------------------------------------------------------


def test_the_default_limit_is_one_megabyte():
    """security.md section 3. Recorded so a change has to be deliberate."""
    assert MAX_BODY_BYTES == 1024 * 1024
