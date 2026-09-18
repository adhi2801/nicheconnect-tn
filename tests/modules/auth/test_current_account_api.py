from collections.abc import Iterator
from datetime import datetime, timedelta

import pytest
from fastapi import APIRouter, FastAPI, Request
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.errors import register_error_handlers
from app.core.rate_limit import limiter
from app.core.request_id import RequestIdMiddleware
from app.db.session import get_db
from app.main import app
from app.modules.auth.dependencies import CurrentBrand, CurrentCreator, get_now
from app.modules.auth.models.account import Account
from app.modules.auth.models.auth_session import AuthSession
from app.modules.auth.sender import FakeOtpSender, get_otp_sender
from app.modules.auth.tokens import create_access_token
from tests.factories import FIXED_NOW, fake_phone

REQUEST_URL = "/api/v1/auth/otp/request"
VERIFY_URL = "/api/v1/auth/otp/verify"
REFRESH_URL = "/api/v1/auth/refresh"
ME_URL = "/api/v1/auth/me"
LOGOUT_ALL_URL = "/api/v1/auth/logout-all"


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


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def assert_problem(response, status: int, code: str) -> dict:
    assert response.status_code == status
    assert response.headers["content-type"] == "application/problem+json"
    body = response.json()
    assert body["code"] == code
    assert body["request_id"] == response.headers["x-request-id"]
    return body


# --- GET /auth/me --------------------------------------------------------


def test_me_returns_the_signed_in_account(client, sender, db):
    login = log_in(client, sender, "brand")

    response = client.get(ME_URL, headers=auth(login["access_token"]))

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == login["account"]["id"]
    assert body["role"] == "brand"
    account = db.get(Account, login["account"]["id"])
    assert body["phone"] == account.phone
    assert body["created_at"].startswith("2026-")


def test_two_accounts_each_see_only_themselves(client, sender):
    first = log_in(client, sender, "creator")
    second = log_in(client, sender, "brand")

    first_me = client.get(ME_URL, headers=auth(first["access_token"])).json()
    second_me = client.get(ME_URL, headers=auth(second["access_token"])).json()

    assert first_me["id"] == first["account"]["id"]
    assert second_me["id"] == second["account"]["id"]
    assert first_me["phone"] != second_me["phone"]


def test_me_without_a_token_is_rejected(client):
    response = client.get(ME_URL)

    assert_problem(response, 401, "invalid_token")
    assert response.headers["www-authenticate"] == "Bearer"


@pytest.mark.parametrize(
    "header",
    [
        {"Authorization": "Bearer not-a-token"},
        {"Authorization": "Bearer "},
        {"Authorization": "Basic abc123"},
        {"Authorization": ""},
    ],
)
def test_me_with_a_bad_authorization_header_is_rejected(client, header):
    assert_problem(client.get(ME_URL, headers=header), 401, "invalid_token")


def test_me_with_an_expired_token_is_rejected(client, sender, clock):
    login = log_in(client, sender)
    clock.advance(timedelta(minutes=15))

    assert_problem(client.get(ME_URL, headers=auth(login["access_token"])), 401, "invalid_token")


def test_me_with_a_token_for_a_deleted_account_is_rejected(client, sender, db, clock):
    login = log_in(client, sender)
    account = db.get(Account, login["account"]["id"])
    db.execute(
        AuthSession.__table__.delete().where(AuthSession.account_id == account.id)
    )
    db.delete(account)
    db.flush()

    assert_problem(client.get(ME_URL, headers=auth(login["access_token"])), 401, "invalid_token")


def test_token_whose_role_no_longer_matches_is_rejected(client, sender, db, clock):
    login = log_in(client, sender, "creator")
    account = db.get(Account, login["account"]["id"])
    account.role = "brand"
    db.flush()

    assert_problem(client.get(ME_URL, headers=auth(login["access_token"])), 401, "invalid_token")


def test_token_for_an_account_that_never_existed_is_rejected(client, clock):
    import uuid

    stranger_token, _ = create_access_token(uuid.uuid4(), "creator", clock.now)

    assert_problem(client.get(ME_URL, headers=auth(stranger_token)), 401, "invalid_token")


def test_refresh_token_cannot_be_used_as_an_access_token(client, sender):
    login = log_in(client, sender)

    assert_problem(client.get(ME_URL, headers=auth(login["refresh_token"])), 401, "invalid_token")


# --- POST /auth/logout-all -----------------------------------------------


def test_logout_all_ends_every_session_of_the_account(client, sender, db, clock):
    login = log_in(client, sender)
    second_device = client.post(
        REFRESH_URL, json={"refresh_token": login["refresh_token"]}
    ).json()
    clock.advance(timedelta(minutes=1))

    response = client.post(LOGOUT_ALL_URL, headers=auth(second_device["access_token"]))

    assert response.status_code == 200
    assert response.json() == {"sessions_ended": 2}
    sessions = db.scalars(
        select(AuthSession).where(AuthSession.account_id == login["account"]["id"])
    ).all()
    assert all(s.revoked_at is not None for s in sessions)
    assert_problem(
        client.post(REFRESH_URL, json={"refresh_token": second_device["refresh_token"]}),
        401,
        "invalid_token",
    )


def test_logout_all_does_not_touch_another_account(client, sender, db):
    mine = log_in(client, sender)
    theirs = log_in(client, sender)

    client.post(LOGOUT_ALL_URL, headers=auth(mine["access_token"]))

    other_sessions = db.scalars(
        select(AuthSession).where(AuthSession.account_id == theirs["account"]["id"])
    ).all()
    assert all(s.revoked_at is None for s in other_sessions)


def test_logout_all_twice_reports_nothing_left_to_end(client, sender):
    login = log_in(client, sender)
    client.post(LOGOUT_ALL_URL, headers=auth(login["access_token"]))

    response = client.post(LOGOUT_ALL_URL, headers=auth(login["access_token"]))

    assert response.json() == {"sessions_ended": 0}


def test_logout_all_without_a_token_is_rejected(client):
    assert_problem(client.post(LOGOUT_ALL_URL), 401, "invalid_token")


# --- role checks ---------------------------------------------------------


@pytest.fixture
def role_client(db, clock) -> Iterator[TestClient]:
    """A small app exposing one brand-only and one creator-only endpoint."""
    role_app = FastAPI()
    register_error_handlers(role_app)
    role_app.add_middleware(RequestIdMiddleware)
    router = APIRouter()

    @router.get("/brand-only")
    def brand_only(request: Request, account: CurrentBrand) -> dict[str, str]:
        return {"account_id": str(account.id)}

    @router.get("/creator-only")
    def creator_only(request: Request, account: CurrentCreator) -> dict[str, str]:
        return {"account_id": str(account.id)}

    role_app.include_router(router)
    role_app.dependency_overrides[get_db] = lambda: db
    role_app.dependency_overrides[get_now] = lambda: clock.now
    try:
        yield TestClient(role_app)
    finally:
        role_app.dependency_overrides.clear()


def token_for(db, clock, role: str) -> str:
    from tests.factories import create_account

    account = create_account(db, role)
    token, _ = create_access_token(account.id, role, clock.now)
    return token


def test_brand_only_endpoint_allows_a_brand(role_client, db, clock):
    response = role_client.get("/brand-only", headers=auth(token_for(db, clock, "brand")))

    assert response.status_code == 200


def test_brand_only_endpoint_refuses_a_creator(role_client, db, clock):
    response = role_client.get("/brand-only", headers=auth(token_for(db, clock, "creator")))

    assert_problem(response, 403, "role_not_allowed")


def test_creator_only_endpoint_refuses_a_brand(role_client, db, clock):
    response = role_client.get("/creator-only", headers=auth(token_for(db, clock, "brand")))

    assert_problem(response, 403, "role_not_allowed")


def test_role_endpoints_still_need_a_token(role_client):
    assert_problem(role_client.get("/brand-only"), 401, "invalid_token")
