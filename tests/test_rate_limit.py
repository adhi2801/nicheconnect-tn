from pathlib import Path

import pytest
from fastapi.testclient import TestClient

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
