from collections.abc import Iterator
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.rate_limit import limiter
from app.db.session import get_db
from app.main import app
from app.modules.auth.dependencies import get_now
from app.modules.auth.models.auth_session import AuthSession
from app.modules.auth.sender import FakeOtpSender, get_otp_sender
from app.modules.auth.tokens import decode_access_token, hash_refresh_token, new_refresh_token
from tests.factories import FIXED_NOW, fake_phone

REQUEST_URL = "/api/v1/auth/otp/request"
VERIFY_URL = "/api/v1/auth/otp/verify"
REFRESH_URL = "/api/v1/auth/refresh"
LOGOUT_URL = "/api/v1/auth/logout"


class Clock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def advance(self, delta: timedelta) -> None:
        self.now += delta


@pytest.fixture
def clock() -> Clock:
    return Clock(FIXED_NOW)


@pytest.fixture
def sender() -> FakeOtpSender:
    return FakeOtpSender()


@pytest.fixture
def client(db, clock, sender) -> Iterator[TestClient]:
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_now] = lambda: clock.now
    app.dependency_overrides[get_otp_sender] = lambda: sender
    limiter.reset()
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
        limiter.reset()


def log_in(client: TestClient, sender: FakeOtpSender, role: str = "creator") -> dict:
    phone = fake_phone()
    assert client.post(REQUEST_URL, json={"phone": phone}).status_code == 202
    response = client.post(
        VERIFY_URL, json={"phone": phone, "code": sender.last_code_for(phone), "role": role}
    )
    assert response.status_code == 200
    return response.json()


def assert_problem(response, status: int, code: str) -> dict:
    assert response.status_code == status
    assert response.headers["content-type"] == "application/problem+json"
    body = response.json()
    assert body["code"] == code
    assert body["request_id"] == response.headers["x-request-id"]
    return body


def session_by_token(db, refresh_token: str) -> AuthSession | None:
    return db.scalars(
        select(AuthSession).where(AuthSession.token_hash == hash_refresh_token(refresh_token))
    ).first()


# --- POST /auth/refresh --------------------------------------------------


def test_refresh_returns_a_new_pair_of_tokens(client, sender, clock):
    login = log_in(client, sender)
    clock.advance(timedelta(minutes=5))

    response = client.post(REFRESH_URL, json={"refresh_token": login["refresh_token"]})

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert body["access_token"] != login["access_token"]
    assert body["refresh_token"] != login["refresh_token"]
    assert body["expires_in"] == 15 * 60
    assert body["refresh_expires_in"] == 30 * 24 * 60 * 60
    assert body["account"] == {**login["account"], "is_new": False}
    claims = decode_access_token(body["access_token"], clock.now)
    assert str(claims.account_id) == login["account"]["id"]


def test_old_refresh_token_stops_working(client, sender, clock):
    login = log_in(client, sender)
    client.post(REFRESH_URL, json={"refresh_token": login["refresh_token"]})
    clock.advance(timedelta(minutes=1))

    response = client.post(REFRESH_URL, json={"refresh_token": login["refresh_token"]})

    assert_problem(response, 401, "invalid_token")
    assert "access_token" not in response.text


def test_reused_token_ends_every_session_of_that_login(client, sender, clock, db):
    login = log_in(client, sender)
    current = client.post(REFRESH_URL, json={"refresh_token": login["refresh_token"]}).json()
    clock.advance(timedelta(minutes=1))

    client.post(REFRESH_URL, json={"refresh_token": login["refresh_token"]})

    assert_problem(
        client.post(REFRESH_URL, json={"refresh_token": current["refresh_token"]}),
        401,
        "invalid_token",
    )
    assert session_by_token(db, current["refresh_token"]).revoked_at is not None


def test_unknown_token_is_rejected(client):
    assert_problem(
        client.post(REFRESH_URL, json={"refresh_token": new_refresh_token()}),
        401,
        "invalid_token",
    )


def test_expired_token_is_rejected(client, sender, clock):
    login = log_in(client, sender)
    clock.advance(timedelta(days=30))

    assert_problem(
        client.post(REFRESH_URL, json={"refresh_token": login["refresh_token"]}),
        401,
        "invalid_token",
    )


@pytest.mark.parametrize(
    ("body", "field"),
    [
        ({}, "refresh_token"),
        ({"refresh_token": "short"}, "refresh_token"),
        ({"refresh_token": None}, "refresh_token"),
        ({"refresh_token": "a" * 43, "account_id": "sneaky"}, "account_id"),
    ],
)
def test_bad_refresh_body_is_rejected(client, body, field):
    problem = assert_problem(client.post(REFRESH_URL, json=body), 422, "validation_failed")
    assert [error["field"] for error in problem["errors"]] == [field]


def test_refresh_is_rate_limited_per_ip(client, sender):
    login = log_in(client, sender)
    token = login["refresh_token"]
    for _ in range(30):
        client.post(REFRESH_URL, json={"refresh_token": token})

    response = client.post(REFRESH_URL, json={"refresh_token": token})

    assert_problem(response, 429, "rate_limited")
    assert response.headers["retry-after"] == "60"


# --- POST /auth/logout ---------------------------------------------------


def test_logout_returns_204_and_ends_the_login(client, sender, clock, db):
    login = log_in(client, sender)
    clock.advance(timedelta(minutes=5))

    response = client.post(LOGOUT_URL, json={"refresh_token": login["refresh_token"]})

    assert response.status_code == 204
    assert response.content == b""
    assert session_by_token(db, login["refresh_token"]).revoked_at == clock.now


def test_refresh_after_logout_is_rejected(client, sender, clock):
    login = log_in(client, sender)
    client.post(LOGOUT_URL, json={"refresh_token": login["refresh_token"]})
    clock.advance(timedelta(minutes=1))

    assert_problem(
        client.post(REFRESH_URL, json={"refresh_token": login["refresh_token"]}),
        401,
        "invalid_token",
    )


def test_logout_also_ends_tokens_it_was_rotated_from(client, sender, clock, db):
    login = log_in(client, sender)
    current = client.post(REFRESH_URL, json={"refresh_token": login["refresh_token"]}).json()
    clock.advance(timedelta(minutes=1))

    assert client.post(LOGOUT_URL, json={"refresh_token": current["refresh_token"]}).status_code == 204

    assert session_by_token(db, login["refresh_token"]).revoked_at is not None
    assert session_by_token(db, current["refresh_token"]).revoked_at is not None


def test_logout_with_an_unknown_token_also_returns_204(client):
    response = client.post(LOGOUT_URL, json={"refresh_token": new_refresh_token()})

    assert response.status_code == 204


def test_logout_does_not_end_another_login(client, sender, db):
    first = log_in(client, sender)
    second = log_in(client, sender)

    client.post(LOGOUT_URL, json={"refresh_token": first["refresh_token"]})

    assert session_by_token(db, second["refresh_token"]).revoked_at is None


def test_bad_logout_body_is_rejected(client):
    assert_problem(client.post(LOGOUT_URL, json={}), 422, "validation_failed")


def test_tokens_never_reach_the_logs(client, sender, caplog):
    import logging

    with caplog.at_level(logging.DEBUG):
        login = log_in(client, sender)
        refreshed = client.post(
            REFRESH_URL, json={"refresh_token": login["refresh_token"]}
        ).json()
        client.post(LOGOUT_URL, json={"refresh_token": refreshed["refresh_token"]})

    for secret in (
        login["refresh_token"],
        login["access_token"],
        refreshed["refresh_token"],
        refreshed["access_token"],
    ):
        assert secret not in caplog.text
