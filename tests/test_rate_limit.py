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
