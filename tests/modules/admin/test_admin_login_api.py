"""Admins log in with two factors, and every admin hears of it (item 101, D-105).

The phone code alone never makes an admin session any more
(tests/modules/auth/test_admin_login_api.py): here, both codes in one
request, the setup ticket that is the only way to get an authenticator, the
session's 1-hour and 12-hour limits, and the alerts.
"""

import base64
from collections.abc import Iterator
from datetime import timedelta

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update

from app.core.config import settings
from app.core.rate_limit import limiter
from app.main import app
from app.modules.admin import admin_login_service
from app.modules.auth import second_factor
from app.modules.auth.models.account import Account
from app.modules.auth.models.auth_session import AuthSession
from app.modules.auth.models.otp_challenge import OtpChallenge
from app.modules.auth.models.totp_factor import TotpFactor
from app.modules.auth.sender import FakeOtpSender, get_otp_sender
from app.modules.auth.tokens import (
    ALGORITHM,
    CURRENT_KEY_ID,
    create_access_token,
    hash_refresh_token,
    new_refresh_token,
)
from app.modules.notifications.models import Notification
from tests.deal_flow import Clock, User
from tests.factories import build_auth_session, create_account, fake_phone

LOGIN = "/api/v1/auth/admin/login"
SET_UP = "/api/v1/auth/admin/second-factor"
REFRESH = "/api/v1/auth/refresh"
AN_ADMIN_ROUTE = "/api/v1/admin/reports"
ALERTS = (
    "admin_signed_in",
    "admin_second_factor_refused",
    "admin_second_factor_changed",
)


class Sender(FakeOtpSender):
    def __init__(self, clock: Clock) -> None:
        super().__init__()
        self.clock = clock


@pytest.fixture
def sender(client, clock) -> Iterator[Sender]:
    fake = Sender(clock)
    app.dependency_overrides[get_otp_sender] = lambda: fake
    yield fake


@pytest.fixture
def admin(db) -> Account:
    account = create_account(db, "admin")
    # Committed (inside the test's rolled-back transaction), because a
    # refused login rolls its session back.
    db.commit()
    return account


def phone_code(client: TestClient, sender: FakeOtpSender, phone: str) -> str:
    # The per-address send limit counts real seconds; the phone's own limits
    # in the database still apply. Each code a second after the last, so
    # "the latest code" is never a tie, as with a real clock.
    limiter.reset()
    sender.clock.advance(timedelta(seconds=1))
    assert (
        client.post("/api/v1/auth/otp/request", json={"phone": phone}).status_code == 202
    )
    code = sender.last_code_for(phone)
    assert code is not None
    return code


def ticket_for(db, admin: Account, clock: Clock) -> str:
    return admin_login_service.issue_ticket(db, admin, clock.now)


def set_up(client, sender, phone: str, ticket: str):
    return client.post(
        SET_UP,
        json={
            "phone": phone,
            "code": phone_code(client, sender, phone),
            "ticket": ticket,
        },
    )


def enrol(client, db, sender, clock, admin: Account) -> bytes:
    """Give the admin an authenticator; return its secret."""
    response = set_up(client, sender, admin.phone, ticket_for(db, admin, clock))
    assert response.status_code == 201, response.text
    padded = response.json()["secret"] + "=" * (-len(response.json()["secret"]) % 8)
    return base64.b32decode(padded)


def shown(secret: bytes, clock: Clock, steps: int = 0) -> str:
    """What the authenticator app shows now, or `steps` steps from now."""
    return second_factor.code_at_step(secret, second_factor.step_at(clock.now) + steps)


def log_in(client, sender, phone: str, authenticator_code: str):
    return client.post(
        LOGIN,
        json={
            "phone": phone,
            "code": phone_code(client, sender, phone),
            "authenticator_code": authenticator_code,
        },
    )


def wrong(code: str) -> str:
    return f"{(int(code) + 1) % 1_000_000:06d}"


def factor_of(db, admin: Account) -> TotpFactor:
    db.expire_all()
    return db.scalars(select(TotpFactor).where(TotpFactor.account_id == admin.id)).one()


def alerts(
    db, about: Account, kind: str, *, to: Account | None = None
) -> list[Notification]:
    """Alerts of `kind` about this admin, as `to` (the admin themself) received them.

    Counted for one recipient, so an admin left in the database by anything
    else cannot change the count.
    """
    db.expire_all()
    recipient = (to or about).id
    return [
        n
        for n in db.scalars(
            select(Notification).where(
                Notification.notification_type == kind,
                Notification.account_id == recipient,
            )
        ).all()
        if n.details.get("admin_account_id") == str(about.id)
    ]


def told(db, about: Account, kind: str) -> set:
    """Every account that received an alert of `kind` about this admin."""
    db.expire_all()
    return {
        n.account_id
        for n in db.scalars(
            select(Notification).where(Notification.notification_type == kind)
        ).all()
        if n.details.get("admin_account_id") == str(about.id)
    }


def comparable(response) -> tuple[int, dict]:
    body = response.json()
    body.pop("request_id", None)
    body.pop("instance", None)
    return response.status_code, body


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# --- logging in ---------------------------------------------------------------------------


def test_an_admin_logs_in_with_both_codes(client, db, sender, clock, admin):
    secret = enrol(client, db, sender, clock, admin)

    response = log_in(client, sender, admin.phone, shown(secret, clock))

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["account"] == {"id": str(admin.id), "role": "admin", "is_new": False}
    assert response.headers["cache-control"] == "no-store"
    assert body["refresh_expires_in"] == 3600
    claims = jwt.decode(
        body["access_token"],
        settings.secret_key.get_secret_value(),
        algorithms=[ALGORITHM],
        options={"verify_exp": False},
    )
    assert claims["amr"] == ["mfa", "otp"]
    assert (
        client.get(AN_ADMIN_ROUTE, headers=bearer(body["access_token"])).status_code
        == 200
    )


def test_the_code_from_the_step_before_still_works(client, db, sender, clock, admin):
    secret = enrol(client, db, sender, clock, admin)

    response = log_in(client, sender, admin.phone, shown(secret, clock, -1))

    assert response.status_code == 200, response.text


def test_a_wrong_authenticator_code_is_answered_as_a_wrong_phone_code(
    client, db, sender, clock, admin
):
    secret = enrol(client, db, sender, clock, admin)
    stranger = fake_phone()
    phone_code(client, sender, stranger)

    refused = log_in(client, sender, admin.phone, wrong(shown(secret, clock)))
    wrong_phone_code = client.post(
        LOGIN,
        json={"phone": stranger, "code": "000000", "authenticator_code": "123456"},
    )

    assert comparable(refused) == comparable(wrong_phone_code)
    assert refused.json()["code"] == "otp_invalid"


def test_a_refused_authenticator_code_uses_up_the_phone_code_s_attempt(
    client, db, sender, clock, admin
):
    secret = enrol(client, db, sender, clock, admin)

    log_in(client, sender, admin.phone, wrong(shown(secret, clock)))

    db.expire_all()
    challenge = db.scalars(
        select(OtpChallenge)
        .where(OtpChallenge.phone == admin.phone)
        .order_by(OtpChallenge.created_at.desc())
    ).first()
    assert challenge.attempts == 1
    assert challenge.consumed_at is None
    assert factor_of(db, admin).consecutive_failures == 1
    assert (
        db.scalars(select(AuthSession).where(AuthSession.account_id == admin.id)).all()
        == []
    )


def test_a_wrong_phone_code_is_refused_whatever_the_authenticator_says(
    client, db, sender, clock, admin
):
    secret = enrol(client, db, sender, clock, admin)
    phone_code(client, sender, admin.phone)

    response = client.post(
        LOGIN,
        json={
            "phone": admin.phone,
            "code": wrong(sender.last_code_for(admin.phone)),
            "authenticator_code": shown(secret, clock),
        },
    )

    assert response.status_code == 400
    # A wrong phone code tells nobody: there was no partial success.
    assert alerts(db, admin, "admin_second_factor_refused") == []


@pytest.mark.parametrize("role", ["brand", "creator"])
def test_a_number_that_is_not_an_admin_s_is_a_wrong_code(client, db, sender, role):
    user = create_account(db, role)
    db.commit()

    response = log_in(client, sender, user.phone, "123456")

    assert response.status_code == 400
    assert response.json()["code"] == "otp_invalid"
    assert db.get(Account, user.id).role == role
    assert alerts(db, user, "admin_second_factor_refused") == []


def test_an_unknown_number_is_a_wrong_code(client, db, sender):
    phone = fake_phone()

    response = log_in(client, sender, phone, "123456")

    assert response.status_code == 400
    assert db.scalars(select(Account).where(Account.phone == phone)).first() is None


def test_an_admin_without_an_authenticator_cannot_log_in(client, db, sender, admin):
    response = log_in(client, sender, admin.phone, "123456")

    assert response.status_code == 400
    assert response.json()["code"] == "otp_invalid"
    (alert,) = alerts(db, admin, "admin_second_factor_refused")
    assert alert.details["reason"] == "not_set_up"


def test_an_admin_waiting_for_setup_cannot_log_in(client, db, sender, clock, admin):
    ticket_for(db, admin, clock)

    response = log_in(client, sender, admin.phone, "123456")

    assert response.status_code == 400
    (alert,) = alerts(db, admin, "admin_second_factor_refused")
    assert alert.details["reason"] == "not_set_up"


def test_a_code_works_once_even_with_a_new_phone_code(client, db, sender, clock, admin):
    secret = enrol(client, db, sender, clock, admin)
    code = shown(secret, clock)
    assert log_in(client, sender, admin.phone, code).status_code == 200

    replayed = log_in(client, sender, admin.phone, code)

    assert replayed.status_code == 400
    (alert,) = alerts(db, admin, "admin_second_factor_refused")
    assert alert.details == {
        "admin_account_id": str(admin.id),
        "reason": "wrong_code",
        "locked": False,
    }


def test_the_next_step_s_code_works_after_one_was_used(client, db, sender, clock, admin):
    secret = enrol(client, db, sender, clock, admin)
    assert log_in(client, sender, admin.phone, shown(secret, clock)).status_code == 200

    clock.advance(timedelta(seconds=second_factor.PERIOD_SECONDS))

    assert log_in(client, sender, admin.phone, shown(secret, clock)).status_code == 200


def test_the_tenth_wrong_code_in_a_row_locks_it(client, db, sender, clock, admin):
    secret = enrol(client, db, sender, clock, admin)
    db.execute(
        update(TotpFactor)
        .where(TotpFactor.account_id == admin.id)
        .values(consecutive_failures=9)
    )
    db.commit()

    log_in(client, sender, admin.phone, wrong(shown(secret, clock)))
    locked_when = clock.now
    then_right = log_in(client, sender, admin.phone, shown(secret, clock))

    assert then_right.status_code == 400
    assert factor_of(db, admin).locked_at == locked_when
    locking, after = alerts(db, admin, "admin_second_factor_refused")
    assert (locking.details["reason"], locking.details["locked"]) == ("wrong_code", True)
    assert (after.details["reason"], after.details["locked"]) == ("locked", False)


def test_ten_wrong_codes_spread_out_still_lock_it(client, db, sender, clock, admin):
    """The count is of failures in a row, not in a window: patience buys nothing."""
    secret = enrol(client, db, sender, clock, admin)

    for _ in range(10):
        # Apart enough for the phone's own limits: 3 codes in 10 minutes, 10 a day.
        clock.advance(timedelta(hours=3))
        log_in(client, sender, admin.phone, wrong(shown(secret, clock)))

    assert factor_of(db, admin).locked_at is not None


def test_a_right_code_clears_the_failures(client, db, sender, clock, admin):
    secret = enrol(client, db, sender, clock, admin)
    log_in(client, sender, admin.phone, wrong(shown(secret, clock)))

    assert log_in(client, sender, admin.phone, shown(secret, clock)).status_code == 200

    assert factor_of(db, admin).consecutive_failures == 0


def test_a_suspended_admin_is_told_so(client, db, sender, clock, admin):
    secret = enrol(client, db, sender, clock, admin)
    db.execute(
        update(Account)
        .where(Account.id == admin.id)
        .values(suspended_at=clock.now, suspension_reason="abuse")
    )
    db.commit()

    response = log_in(client, sender, admin.phone, shown(secret, clock))

    assert response.status_code == 403
    assert response.json()["code"] == "account_suspended"


# --- every admin is told ------------------------------------------------------------------


def test_every_active_admin_is_told_of_a_sign_in(client, db, sender, clock, admin):
    other = create_account(db, "admin")
    suspended = create_account(
        db, "admin", suspended_at=clock.now, suspension_reason="abuse"
    )
    db.commit()
    secret = enrol(client, db, sender, clock, admin)

    log_in(client, sender, admin.phone, shown(secret, clock))

    recipients = told(db, admin, "admin_signed_in")
    assert {admin.id, other.id} <= recipients
    assert suspended.id not in recipients


def test_a_ticket_and_a_setup_are_each_told_to_every_admin(
    client, db, sender, clock, admin
):
    other = create_account(db, "admin")
    db.commit()

    enrol(client, db, sender, clock, admin)

    for recipient in (admin, other):
        changes = sorted(
            n.details["change"]
            for n in alerts(db, admin, "admin_second_factor_changed", to=recipient)
        )
        assert changes == ["set_up", "ticket_issued"]


@pytest.mark.parametrize("alert", ALERTS)
def test_no_admin_can_mute_an_alert(client, db, clock, admin, alert):
    response = client.put(
        "/api/v1/me/notification-preferences",
        json={
            "quiet_from": None,
            "quiet_until": None,
            "digest": "off",
            "digest_hour": 9,
            "muted_types": [alert],
        },
        headers=User(admin.id, "admin", clock).headers,
    )

    assert response.status_code == 422, response.text
    assert response.json()["code"] == "urgent_type_not_mutable"


# --- setting up an authenticator ------------------------------------------------------------


def test_a_ticket_gives_a_secret_once(client, db, sender, clock, admin):
    response = set_up(client, sender, admin.phone, ticket_for(db, admin, clock))

    assert response.status_code == 201, response.text
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert body["setup_link"].startswith("otpauth://totp/")
    assert body["secret"] in body["setup_link"]
    assert (body["digits"], body["period_seconds"], body["algorithm"]) == (6, 30, "SHA1")
    factor = factor_of(db, admin)
    assert factor.enrolled_at == clock.now
    assert factor.ticket_hash is None
    secret = base64.b32decode(body["secret"] + "=" * (-len(body["secret"]) % 8))
    assert secret not in factor.secret_ciphertext


def test_a_ticket_works_once(client, db, sender, clock, admin):
    ticket = ticket_for(db, admin, clock)
    assert set_up(client, sender, admin.phone, ticket).status_code == 201

    again = set_up(client, sender, admin.phone, ticket)

    assert again.status_code == 400
    assert again.json()["code"] == "otp_invalid"


def test_a_ticket_lasts_fifteen_minutes(client, db, sender, clock, admin):
    ticket = ticket_for(db, admin, clock)
    clock.advance(timedelta(minutes=15))

    response = set_up(client, sender, admin.phone, ticket)

    assert response.status_code == 400
    (alert,) = alerts(db, admin, "admin_second_factor_refused")
    assert alert.details["reason"] == "bad_ticket"


def test_a_wrong_ticket_is_refused(client, db, sender, clock, admin):
    ticket_for(db, admin, clock)

    response = set_up(client, sender, admin.phone, "example_ticket_not_a_real_one_01")

    assert response.status_code == 400
    assert factor_of(db, admin).secret_ciphertext is None


def test_one_admin_s_ticket_is_no_use_to_another(client, db, sender, clock, admin):
    other = create_account(db, "admin")
    db.commit()
    ticket = ticket_for(db, admin, clock)

    response = set_up(client, sender, other.phone, ticket)

    assert response.status_code == 400
    assert factor_of(db, admin).secret_ciphertext is None


def test_a_new_ticket_ends_the_sessions_and_voids_the_old_authenticator(
    client, db, sender, clock, admin
):
    secret = enrol(client, db, sender, clock, admin)
    tokens = log_in(client, sender, admin.phone, shown(secret, clock)).json()

    ticket_for(db, admin, clock)
    clock.advance(timedelta(seconds=second_factor.PERIOD_SECONDS))

    assert (
        client.post(REFRESH, json={"refresh_token": tokens["refresh_token"]}).status_code
        == 401
    )
    assert log_in(client, sender, admin.phone, shown(secret, clock)).status_code == 400


def test_a_new_ticket_lifts_a_lock(client, db, sender, clock, admin):
    enrol(client, db, sender, clock, admin)
    db.execute(
        update(TotpFactor)
        .where(TotpFactor.account_id == admin.id)
        .values(consecutive_failures=10, locked_at=clock.now)
    )
    db.commit()

    secret = enrol(client, db, sender, clock, admin)

    assert factor_of(db, admin).locked_at is None
    assert log_in(client, sender, admin.phone, shown(secret, clock)).status_code == 200


# --- the session --------------------------------------------------------------------------


def test_an_hour_without_a_refresh_ends_the_session(client, db, sender, clock, admin):
    secret = enrol(client, db, sender, clock, admin)
    tokens = log_in(client, sender, admin.phone, shown(secret, clock)).json()

    clock.advance(timedelta(hours=1))

    response = client.post(REFRESH, json={"refresh_token": tokens["refresh_token"]})
    assert response.status_code == 401


def test_refreshing_never_stretches_a_session_past_twelve_hours(
    client, db, sender, clock, admin
):
    secret = enrol(client, db, sender, clock, admin)
    tokens = log_in(client, sender, admin.phone, shown(secret, clock)).json()
    logged_in_at = clock.now

    while True:
        clock.advance(timedelta(minutes=50))
        limiter.reset()
        response = client.post(REFRESH, json={"refresh_token": tokens["refresh_token"]})
        if response.status_code != 200:
            break
        tokens = response.json()
        # Neither token outlives the 12 hours.
        ends = logged_in_at + timedelta(hours=12)
        assert clock.now + timedelta(seconds=tokens["refresh_expires_in"]) <= ends
        assert clock.now + timedelta(seconds=tokens["expires_in"]) <= ends

    assert response.status_code == 401
    assert clock.now - logged_in_at <= timedelta(hours=12, minutes=50)
    assert clock.now - logged_in_at > timedelta(hours=11)


def test_the_last_access_token_ends_with_the_twelve_hours(
    client, db, sender, clock, admin
):
    """Refreshed with ten minutes left, it lasts ten minutes, not the usual fifteen."""
    secret = enrol(client, db, sender, clock, admin)
    tokens = log_in(client, sender, admin.phone, shown(secret, clock)).json()
    ends = clock.now + timedelta(hours=12)
    for _ in range(14):
        clock.advance(timedelta(minutes=50))
        limiter.reset()
        tokens = client.post(
            REFRESH, json={"refresh_token": tokens["refresh_token"]}
        ).json()
    clock.advance(ends - timedelta(minutes=10) - clock.now)

    response = client.post(REFRESH, json={"refresh_token": tokens["refresh_token"]})

    assert response.status_code == 200, response.text
    assert response.json()["expires_in"] == 600
    assert response.json()["refresh_expires_in"] == 600


def test_a_session_made_from_the_phone_code_alone_is_ended_at_refresh(
    db, client, admin, clock
):
    refresh_token = new_refresh_token()
    db.add(
        build_auth_session(
            db,
            account_id=admin.id,
            token_hash=hash_refresh_token(refresh_token),
            expires_at=clock.now + timedelta(hours=1),
        )
    )
    db.commit()

    response = client.post(REFRESH, json={"refresh_token": refresh_token})

    assert response.status_code == 401
    db.expire_all()
    session = db.scalars(
        select(AuthSession).where(AuthSession.account_id == admin.id)
    ).one()
    assert session.revoked_at is not None


def test_an_admin_token_from_the_phone_code_alone_reaches_no_admin_route(
    client, clock, admin
):
    token, _ = create_access_token(admin.id, "admin", clock.now)

    response = client.get(AN_ADMIN_ROUTE, headers=bearer(token))

    assert response.status_code == 404
    assert response.json()["code"] == "not_found"


def test_an_admin_token_from_before_the_second_factor_reaches_no_admin_route(
    client, clock, admin
):
    """A token signed before D-105 has no `amr` at all."""
    claims = {
        "sub": str(admin.id),
        "role": "admin",
        "typ": "access",
        "iat": int(clock.now.timestamp()),
        "exp": int((clock.now + timedelta(minutes=15)).timestamp()),
        "jti": "0" * 32,
    }
    token = jwt.encode(
        claims,
        settings.secret_key.get_secret_value(),
        algorithm=ALGORITHM,
        headers={"kid": CURRENT_KEY_ID},
    )

    response = client.get(AN_ADMIN_ROUTE, headers=bearer(token))

    assert response.status_code == 404


# --- the requests themselves --------------------------------------------------------------


@pytest.mark.parametrize(
    "body",
    [
        {"phone": "+919876543210", "code": "123456", "authenticator_code": "12345"},
        {"phone": "+919876543210", "code": "123456", "authenticator_code": "abcdef"},
        {"phone": "+919876543210", "code": "123456"},
        {
            "phone": "+919876543210",
            "code": "123456",
            "authenticator_code": "123456",
            "role": "admin",
        },
    ],
)
def test_a_malformed_login_is_refused(client, body):
    response = client.post(LOGIN, json=body)

    assert response.status_code == 422
    assert response.json()["code"] == "validation_failed"


@pytest.mark.parametrize(
    "ticket", ["short", "x" * 33, "has spaces in it, thirty-two!!!!"]
)
def test_a_malformed_ticket_is_refused(client, ticket):
    response = client.post(
        SET_UP, json={"phone": "+919876543210", "code": "123456", "ticket": ticket}
    )

    assert response.status_code == 422


@pytest.mark.parametrize("url", [LOGIN, SET_UP])
def test_both_routes_are_rate_limited(client, url):
    body = {
        "phone": "+919876543210",
        "code": "123456",
        "authenticator_code": "123456",
        "ticket": "example_ticket_not_a_real_one_01",
    }
    if url == LOGIN:
        del body["ticket"]
    else:
        del body["authenticator_code"]

    answers = [client.post(url, json=body).status_code for _ in range(11)]

    assert answers[-1] == 429
    assert 429 not in answers[:10]


def test_the_export_shows_the_factor_but_never_its_secret(
    client, db, sender, clock, admin
):
    secret = enrol(client, db, sender, clock, admin)
    factor = factor_of(db, admin)

    # An admin's second check is the authenticator's code (item 82).
    response = client.get(
        "/api/v1/me/export",
        headers={
            **User(admin.id, "admin", clock).headers,
            "Step-Up-Code": shown(secret, clock),
        },
    )

    assert response.status_code == 200, response.text
    (row,) = response.json()["data"]["second_factor"]
    assert row["id"] == str(factor.id)
    assert "secret_ciphertext" not in row
    assert "ticket_hash" not in row
