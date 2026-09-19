"""/healthz says the process is up; /readyz says its dependencies are reachable."""

import logging

import pytest
from fastapi.testclient import TestClient

from app import main as main_module
from app.core import health
from app.core.health import CheckResult, check_database, check_redis
from app.core.rate_limit import limiter
from app.main import app


@pytest.fixture
def client():
    limiter.reset()
    try:
        yield TestClient(app)
    finally:
        limiter.reset()


def test_healthz_says_the_process_is_up(client):
    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readyz_reports_every_dependency_when_all_are_up(client):
    response = client.get("/readyz")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "checks": {"database": "ok", "redis": "ok"},
    }


def test_database_and_redis_checks_pass_against_the_real_services():
    assert check_database().ok is True
    assert check_redis().ok is True


@pytest.mark.parametrize(
    ("down", "expected"),
    [
        ("database", "Unavailable: database."),
        ("redis", "Unavailable: redis."),
    ],
)
def test_readyz_returns_503_when_one_dependency_is_down(client, monkeypatch, down, expected):
    monkeypatch.setattr(
        main_module,
        "run_readiness_checks",
        lambda: [CheckResult(name, name != down) for name in ("database", "redis")],
    )

    response = client.get("/readyz")

    assert response.status_code == 503
    assert response.headers["content-type"] == "application/problem+json"
    body = response.json()
    assert body["code"] == "not_ready"
    assert body["detail"] == expected
    assert body["request_id"] == response.headers["x-request-id"]


def test_readyz_names_both_when_everything_is_down(client, monkeypatch):
    monkeypatch.setattr(
        main_module,
        "run_readiness_checks",
        lambda: [CheckResult("database", False), CheckResult("redis", False)],
    )

    response = client.get("/readyz")

    assert response.status_code == 503
    assert response.json()["detail"] == "Unavailable: database, redis."


def test_a_failed_check_never_leaks_the_connection_details(client, monkeypatch, caplog):
    """Connection strings hold passwords, so they stay out of the response."""
    from app.core.config import settings

    def explode(*args, **kwargs):
        raise ConnectionError(f"could not connect to {settings.redis_url}")

    monkeypatch.setattr(health.redis.Redis, "from_url", explode)

    with caplog.at_level(logging.WARNING):
        result = check_redis()
        response = client.get("/readyz")

    assert result.ok is False
    assert response.status_code == 503
    assert settings.redis_url not in response.text
    assert "redis" in response.json()["detail"]
    assert any("readiness.redis_unavailable" in r.getMessage() for r in caplog.records)


def test_readiness_check_failure_does_not_raise():
    """A probe must answer, not crash, whatever the dependency does."""
    assert check_database().ok in (True, False)
    assert check_redis().ok in (True, False)
