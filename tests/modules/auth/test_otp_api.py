import logging
from collections.abc import Iterator
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.rate_limit import limiter
from app.db.session import get_db
from app.main import app
from app.modules.auth.dependencies import get_now
from app.modules.auth.models.account import Account
from app.modules.auth.models.otp_challenge import OtpChallenge
from app.modules.auth.sender import FakeOtpSender, get_otp_sender
from app.modules.auth.tokens import decode_access_token
from tests.factories import FIXED_NOW, create_account, fake_phone

REQUEST_URL = "/api/v1/auth/otp/request"
VERIFY_URL = "/api/v1/auth/otp/verify"


class Clock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def advance(self, delta: timedelta) -> None:
        self.now += delta


class FailingSender:
    """A provider that fails with an error message echoing the phone and code."""

    def __init__(self) -> None:
        self.attempted_code: str | None = None

    def send_code(self, phone: str, code: str) -> None:
        self.attempted_code = code
        raise ConnectionError(f"provider down while sending {code} to {phone}")


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


def request_code(client: TestClient, sender: FakeOtpSender, phone: str) -> str:
    response = client.post(REQUEST_URL, json={"phone": phone})
    assert response.status_code == 202
    return sender.last_code_for(phone)


def verify(client: TestClient, phone: str, code: str, role: str = "creator"):
    return client.post(VERIFY_URL, json={"phone": phone, "code": code, "role": role})


def wrong(code: str) -> str:
    return "000000" if code != "000000" else "111111"


def assert_problem(response, status: int, code: str) -> dict:
    assert response.status_code == status
    assert response.headers["content-type"] == "application/problem+json"
    body = response.json()
    assert body["code"] == code
    assert body["request_id"] == response.headers["x-request-id"]
    return body


# --- POST /otp/request ---------------------------------------------------


def test_request_accepts_and_sends_a_code(client, sender, db):
    phone = fake_phone()

    response = client.post(REQUEST_URL, json={"phone": phone})

    assert response.status_code == 202
    assert response.json() == {"expires_in_seconds": 300}
    assert response.headers["x-request-id"]
    code = sender.last_code_for(phone)
    assert code is not None and len(code) == 6
    stored = db.scalars(select(OtpChallenge).where(OtpChallenge.phone == phone)).one()
    assert code not in stored.code_hash


def test_request_normalises_the_phone_before_sending(client, sender):
    response = client.post(REQUEST_URL, json={"phone": "+91 88888 00077"})

    assert response.status_code == 202
    assert sender.last_code_for("+918888800077") is not None


def test_request_response_is_identical_for_registered_and_unknown_numbers(client, db):
    registered = create_account(db, "brand").phone

    for_registered = client.post(REQUEST_URL, json={"phone": registered})
    for_unknown = client.post(REQUEST_URL, json={"phone": fake_phone()})

    assert for_registered.status_code == for_unknown.status_code == 202
    assert for_registered.json() == for_unknown.json()
    ignored = {"x-request-id", "date"}
    assert {k for k in for_registered.headers if k not in ignored} == {
        k for k in for_unknown.headers if k not in ignored
    }


@pytest.mark.parametrize("body", [{"phone": "12345"}, {}, {"phone": None}])
def test_request_with_bad_phone_is_rejected_and_sends_nothing(client, sender, body):
    response = client.post(REQUEST_URL, json=body)

    problem = assert_problem(response, 422, "validation_failed")
    assert [error["field"] for error in problem["errors"]] == ["phone"]
    assert sender.sent == []


def test_request_with_unknown_field_is_rejected(client):
    response = client.post(REQUEST_URL, json={"phone": fake_phone(), "role": "admin"})

    problem = assert_problem(response, 422, "validation_failed")
    assert [error["field"] for error in problem["errors"]] == ["role"]


def test_fourth_code_for_a_phone_gets_429_with_exact_retry_after(client, clock, sender):
    phone = fake_phone()
    for minute in (0, 2, 4):
        clock.now = FIXED_NOW + timedelta(minutes=minute)
        request_code(client, sender, phone)
        limiter.reset()  # isolate the per-phone limit from the per-IP limit

    clock.now = FIXED_NOW + timedelta(minutes=5)
    response = client.post(REQUEST_URL, json={"phone": phone})

    assert_problem(response, 429, "otp_send_limit_reached")
    # The first code (minute 0) leaves the 10-minute window at minute 10.
    assert response.headers["retry-after"] == str(5 * 60)
    assert len(sender.sent) == 3


def test_fourth_request_from_one_ip_gets_429(client, sender):
    for _ in range(3):
        request_code(client, sender, fake_phone())

    response = client.post(REQUEST_URL, json={"phone": fake_phone()})

    assert_problem(response, 429, "rate_limited")
    assert response.headers["retry-after"] == "600"
    assert len(sender.sent) == 3


def test_send_failure_does_not_break_the_request(client, caplog):
    failing = FailingSender()
    app.dependency_overrides[get_otp_sender] = lambda: failing
    phone = fake_phone()

    with caplog.at_level(logging.DEBUG):
        response = client.post(REQUEST_URL, json={"phone": phone})

    assert response.status_code == 202
    failures = [r for r in caplog.records if r.getMessage().startswith("otp.send_failed")]
    assert [r.getMessage() for r in failures] == ["otp.send_failed error_type=ConnectionError"]
    assert failures[0].exc_info is None
    # caplog.text is the full formatted output, including any tracebacks.
    assert failing.attempted_code is not None
    assert failing.attempted_code not in caplog.text
    assert phone not in caplog.text
    assert phone[3:] not in caplog.text


# --- POST /otp/verify ----------------------------------------------------


def test_verify_logs_in_a_new_creator(client, sender, clock, db):
    phone = fake_phone()
    code = request_code(client, sender, phone)

    response = verify(client, phone, code, "creator")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == 15 * 60
    assert body["refresh_expires_in"] == 30 * 24 * 60 * 60
    assert body["account"]["role"] == "creator"
    assert body["account"]["is_new"] is True
    claims = decode_access_token(body["access_token"], clock.now)
    assert str(claims.account_id) == body["account"]["id"]
    account = db.scalars(select(Account).where(Account.phone == phone)).one()
    assert str(account.id) == body["account"]["id"]


def test_verify_logs_in_an_existing_brand(client, sender, db):
    account = create_account(db, "brand")
    code = request_code(client, sender, account.phone)

    response = verify(client, account.phone, code, "brand")

    assert response.status_code == 200
    assert response.json()["account"] == {
        "id": str(account.id),
        "role": "brand",
        "is_new": False,
    }


def test_verify_accepts_the_phone_in_another_format(client, sender):
    code = request_code(client, sender, "+918888800088")

    response = verify(client, "88888 00088", code)

    assert response.status_code == 200


def test_wrong_code_gets_400_and_no_tokens(client, sender):
    phone = fake_phone()
    code = request_code(client, sender, phone)

    response = verify(client, phone, wrong(code))

    body = assert_problem(response, 400, "otp_invalid")
    assert body["title"] == "That code is not valid. Check it or request a new one"
    assert "access_token" not in response.text


def test_expired_code_gets_400(client, sender, clock):
    phone = fake_phone()
    code = request_code(client, sender, phone)
    clock.advance(timedelta(minutes=5))

    assert_problem(verify(client, phone, code), 400, "otp_invalid")


def test_used_code_gets_400(client, sender):
    phone = fake_phone()
    code = request_code(client, sender, phone)
    assert verify(client, phone, code).status_code == 200

    assert_problem(verify(client, phone, code), 400, "otp_invalid")


def test_verify_without_requesting_a_code_gets_400(client):
    assert_problem(verify(client, fake_phone(), "123456"), 400, "otp_invalid")


def test_all_code_failures_look_the_same(client, sender, clock):
    wrong_phone, expired_phone = fake_phone(), fake_phone()
    wrong_code = wrong(request_code(client, sender, wrong_phone))
    expired_code = request_code(client, sender, expired_phone)
    clock.advance(timedelta(minutes=6))

    bodies = [
        verify(client, wrong_phone, wrong_code).json(),
        verify(client, expired_phone, expired_code).json(),
        verify(client, fake_phone(), "123456").json(),
    ]

    for body in bodies:
        body.pop("request_id")
    assert bodies[0] == bodies[1] == bodies[2]


def test_role_mismatch_gets_409(client, sender, db):
    account = create_account(db, "brand")
    code = request_code(client, sender, account.phone)

    assert_problem(verify(client, account.phone, code, "creator"), 409, "role_mismatch")
    assert verify(client, account.phone, code, "brand").status_code == 200


@pytest.mark.parametrize(
    ("body", "fields"),
    [
        ({"phone": "9999900001", "code": "12345", "role": "creator"}, ["code"]),
        ({"phone": "123", "code": "123456", "role": "creator"}, ["phone"]),
        ({"phone": "9999900001", "code": "123456", "role": "admin"}, ["role"]),
        ({"phone": "9999900001", "code": "123456"}, ["role"]),
        ({"phone": "9999900001", "code": "123456", "role": "creator", "is_admin": True}, ["is_admin"]),
    ],
)
def test_verify_with_invalid_fields_gets_422(client, body, fields):
    problem = assert_problem(client.post(VERIFY_URL, json=body), 422, "validation_failed")
    assert [error["field"] for error in problem["errors"]] == fields


def test_eleventh_verify_from_one_ip_gets_429(client, sender):
    phone = fake_phone()
    code = request_code(client, sender, phone)
    for _ in range(10):
        assert verify(client, phone, wrong(code)).status_code == 400

    response = verify(client, phone, code)

    assert_problem(response, 429, "rate_limited")
    assert response.headers["retry-after"] == "600"


# --- privacy -------------------------------------------------------------


def test_codes_phones_and_tokens_never_reach_the_logs(client, sender, caplog):
    phone = fake_phone()
    with caplog.at_level(logging.DEBUG):
        code = request_code(client, sender, phone)
        verify(client, phone, wrong(code))
        body = verify(client, phone, code).json()

    # caplog.text is the full formatted output, including any tracebacks.
    for secret in (phone, phone[3:], code, body["access_token"], body["refresh_token"]):
        assert secret not in caplog.text
