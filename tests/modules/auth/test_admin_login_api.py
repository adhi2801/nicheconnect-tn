"""Admins log in like everyone else, and login never makes anyone an admin (D-061)."""

from collections.abc import Iterator
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.core.rate_limit import limiter
from app.db.session import get_db
from app.main import app
from app.modules.auth.dependencies import get_now
from app.modules.auth.models.account import Account
from app.modules.auth.models.auth_session import ADMIN_REFRESH_TOKEN_DAYS, AuthSession
from app.modules.auth.models.otp_challenge import OtpChallenge
from app.modules.auth.sender import FakeOtpSender, get_otp_sender
from tests.factories import FIXED_NOW, create_account, fake_phone

REQUEST_URL = "/api/v1/auth/otp/request"
VERIFY_URL = "/api/v1/auth/otp/verify"


@pytest.fixture
def sender() -> FakeOtpSender:
    return FakeOtpSender()


@pytest.fixture
def client(db, sender) -> Iterator[TestClient]:
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_now] = lambda: FIXED_NOW
    app.dependency_overrides[get_otp_sender] = lambda: sender
    limiter.reset()
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
        limiter.reset()


def code_for(client, sender, phone: str) -> str:
    assert client.post(REQUEST_URL, json={"phone": phone}).status_code == 202
    return sender.last_code_for(phone)


def verify(client, phone: str, code: str, role: str):
    return client.post(VERIFY_URL, json={"phone": phone, "code": code, "role": role})


def comparable(response) -> tuple[int, dict]:
    """Status and body, minus what differs between any two requests."""
    body = response.json()
    body.pop("request_id", None)
    body.pop("instance", None)
    return response.status_code, body


def test_an_admin_logs_in_with_a_code(client, db, sender):
    admin = create_account(db, "admin")

    response = verify(client, admin.phone, code_for(client, sender, admin.phone), "admin")

    assert response.status_code == 200, response.text
    assert response.json()["account"] == {
        "id": str(admin.id),
        "role": "admin",
        "is_new": False,
    }


def test_an_admin_session_lasts_one_day_not_thirty(client, db, sender):
    admin = create_account(db, "admin")

    verify(client, admin.phone, code_for(client, sender, admin.phone), "admin")

    session = db.scalars(
        select(AuthSession).where(AuthSession.account_id == admin.id)
    ).one()
    assert session.expires_at - FIXED_NOW == timedelta(days=ADMIN_REFRESH_TOKEN_DAYS)


def test_login_never_creates_an_admin(client, db, sender):
    phone = fake_phone()

    response = verify(client, phone, code_for(client, sender, phone), "admin")

    assert response.status_code == 400
    assert response.json()["code"] == "otp_invalid"
    assert db.scalar(select(func.count()).where(Account.phone == phone)) == 0


def test_a_user_cannot_log_in_as_admin(client, db, sender):
    brand = create_account(db, "brand")

    response = verify(client, brand.phone, code_for(client, sender, brand.phone), "admin")

    assert response.status_code == 400
    assert response.json()["code"] == "otp_invalid"
    assert db.get(Account, brand.id).role == "brand"


def test_asking_for_admin_looks_exactly_like_a_wrong_code(client, db, sender):
    """So nobody can learn which phones belong to admins, or that none do."""
    phone_a, phone_b = fake_phone(), fake_phone()
    right_code = code_for(client, sender, phone_a)
    code_for(client, sender, phone_b)

    as_admin = verify(client, phone_a, right_code, "admin")
    wrong_code = verify(client, phone_b, "000000", "creator")

    assert comparable(as_admin) == comparable(wrong_code)


def test_asking_for_admin_uses_up_an_attempt_like_a_wrong_code(client, db, sender):
    phone = fake_phone()
    code = code_for(client, sender, phone)

    verify(client, phone, code, "admin")

    challenge = db.scalars(select(OtpChallenge).where(OtpChallenge.phone == phone)).one()
    assert challenge.attempts == 1
    assert challenge.consumed_at is None


def test_the_same_code_then_works_for_the_role_the_person_really_has(client, db, sender):
    phone = fake_phone()
    code = code_for(client, sender, phone)
    verify(client, phone, code, "admin")

    response = verify(client, phone, code, "creator")

    assert response.status_code == 200


def test_an_admin_cannot_log_in_as_a_brand(client, db, sender):
    admin = create_account(db, "admin")

    response = verify(client, admin.phone, code_for(client, sender, admin.phone), "brand")

    assert response.status_code == 409
    assert response.json()["code"] == "role_mismatch"
