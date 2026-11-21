from collections import Counter
from pathlib import Path

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from app.core.errors import _leaf_routes
from app.core.rate_limit import limiter
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_limiter():
    limiter.reset()
    yield
    limiter.reset()


def test_healthz_returns_429_over_limit():
    for _ in range(60):
        resp = client.get("/healthz")
        assert resp.status_code == 200

    resp = client.get("/healthz")
    assert resp.status_code == 429


def test_rate_limited_response_uses_problem_details_with_retry_after():
    for _ in range(60):
        client.get("/healthz")

    resp = client.get("/healthz", headers={"X-Request-ID": "trace-429"})

    assert resp.status_code == 429
    assert resp.headers["content-type"] == "application/problem+json"
    assert resp.headers["retry-after"] == "60"
    assert resp.headers["x-request-id"] == "trace-429"
    body = resp.json()
    assert body["code"] == "rate_limited"
    assert body["status"] == 429
    assert body["request_id"] == "trace-429"


def test_successful_response_has_request_id():
    resp = client.get("/healthz")

    assert resp.status_code == 200
    assert resp.headers["x-request-id"]


def limiter_keys() -> Counter[str]:
    """How many routes answer to each counter name the limiter keeps.

    slowapi names a route's limits, and keys its counters, by the endpoint
    function's module and name (`key_style="endpoint"`, D-137), not by the
    route.
    """
    return Counter(
        f"{route.endpoint.__module__}.{route.endpoint.__name__}"
        for route in _leaf_routes(app.routes)
        if isinstance(route, APIRoute)
    )


def test_the_routes_are_found():
    # An empty walk would prove nothing (testing.md section 2).
    assert len(limiter_keys()) > 200


def test_no_two_routes_share_a_rate_limit_counter():
    """Audit C13, 22 November 2026. Routes made by one factory function
    (`_brand_move` and its kind) were all called `endpoint`, so slowapi gave
    them one name: the five deal memo moves shared one counter and stacked
    five copies of their limit on it, so each move cost five of the thirty a
    minute, and a send counted against a later accept. Shortlisting and
    accepting an application, and a campaign's status moves, did the same.
    """
    shared = {key: count for key, count in limiter_keys().items() if count > 1}

    assert shared == {}


def test_routers_use_the_typed_rate_limit_decorator():
    """`limiter.limit` hides every endpoint's type from mypy, and nothing in
    ruff or mypy would notice it coming back (app/core/rate_limit.py)."""
    app_dir = Path(__file__).resolve().parents[1] / "app" / "modules"
    offenders = [
        str(path.relative_to(app_dir))
        for path in app_dir.rglob("*.py")
        if "@limiter.limit(" in path.read_text(encoding="utf-8")
    ]

    assert offenders == [], "Use @rate_limit(...) instead in: " + ", ".join(offenders)
