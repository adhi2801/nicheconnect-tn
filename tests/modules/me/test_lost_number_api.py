"""Changing the phone number when the current one is lost (D-110), through the API.

No code from the current number, so the login is the proof: at least 30 days
old, then a code from the new number and a 7-day wait. Any login with the
current number meanwhile cancels it, since the number was not lost after
all, and the account is told. A change with both numbers is never cancelled
that way.
"""

from collections.abc import Iterator
from contextlib import nullcontext
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.main import app
from app.modules.auth.login_age import LOST_NUMBER_LOGIN
from app.modules.auth.models.account import Account
from app.modules.auth.models.account_phone_change import (
    PHONE_CHANGE_WAIT,
    PHONE_CHANGE_WAIT_WITHOUT_CURRENT,
    AccountPhoneChange,
)
from app.modules.auth.sender import FakeOtpSender, get_otp_sender
from app.modules.me import phone_change_service as service
from app.modules.notifications.models import Notification
from tests.deal_flow import User, creator_user
from tests.factories import create_account, unique_test_phone
from tests.step_up import STEP_UP_URL, download_export

URL = "/api/v1/me/phone-change"
LOST_URL = "/api/v1/me/phone-change/without-current-number"
OTP_REQUEST_URL = "/api/v1/auth/otp/request"
OTP_VERIFY_URL = "/api/v1/auth/otp/verify"
REFRESH_URL = "/api/v1/auth/refresh"
ATTENTION_URL = "/api/v1/me/attention"


@pytest.fixture
def sender(client) -> Iterator[FakeOtpSender]:
    fake = FakeOtpSender()
    app.dependency_overrides[get_otp_sender] = lambda: fake
    yield fake
    app.dependency_overrides.pop(get_otp_sender, None)


@pytest.fixture
def creator(db, clock) -> User:
    user = creator_user(db, clock)
    db.commit()
    return user


def phone_of(db, user: User) -> str:
    return db.scalars(
        select(Account.phone)
        .where(Account.id == user.account_id)
        .execution_options(populate_existing=True)
    ).one()


def login_code(client, sender, phone: str) -> str:
    response = client.post(OTP_REQUEST_URL, json={"phone": phone})
    assert response.status_code == 202, response.text
    code = sender.last_code_for(phone)
    assert code is not None
    return code


def lost(client, sender, headers, new_phone: str, *, code: str | None = None):
    new_code = code if code is not None else login_code(client, sender, new_phone)
    return client.post(
        LOST_URL,
        json={"new_phone": new_phone, "new_phone_code": new_code},
        headers=headers,
    )


def log_in(client, sender, phone: str):
    code = login_code(client, sender, phone)
    return client.post(
        OTP_VERIFY_URL, json={"phone": phone, "code": code, "role": "creator"}
    ).json()


def run_job(db, clock) -> service.ChangeRun:
    return service.run_changes(lambda: nullcontext(db), clock.now)


def told(db, account_id, kind: str) -> list[Notification]:
    return list(
        db.scalars(
            select(Notification).where(
                Notification.account_id == account_id,
                Notification.notification_type == kind,
            )
        ).all()
    )


def waiting_row(db, user: User) -> AccountPhoneChange | None:
    return db.scalars(
        select(AccountPhoneChange)
        .where(AccountPhoneChange.account_id == user.account_id)
        .execution_options(populate_existing=True)
    ).first()


def assert_problem(response, status: int, code: str) -> None:
    assert response.status_code == status, response.text
    assert response.json()["code"] == code


def stamp(moment) -> str:
    return moment.isoformat().replace("+00:00", "Z")


# --- asking ----------------------------------------------------------------------------


def test_a_lost_number_change_needs_no_code_from_it_and_waits_seven_days(
    client, db, sender, clock, creator
):
    new_phone = unique_test_phone()

    response = lost(client, sender, creator.headers, new_phone)

    assert response.status_code == 202, response.text
    takes_effect_at = clock.now + PHONE_CHANGE_WAIT_WITHOUT_CURRENT
    assert response.json()["waiting"] == {
        "new_phone": new_phone,
        "requested_at": stamp(clock.now),
        "takes_effect_at": stamp(takes_effect_at),
        "without_current_number": True,
    }
    [notice] = told(db, creator.account_id, "phone_change_requested")
    assert notice.details == {
        "takes_effect_at": takes_effect_at.isoformat(),
        "without_current_number": True,
    }


def test_a_change_with_both_numbers_says_it_was_not_without_one(
    client, db, sender, clock, creator
):
    new_phone = unique_test_phone()
    asked = client.post(
        STEP_UP_URL,
        json={"action": "change_phone", "new_phone": new_phone},
        headers=creator.headers,
    )
    assert asked.status_code == 202
    current_code = sender.last_code_for(phone_of(db, creator))
    new_code = login_code(client, sender, new_phone)

    response = client.post(
        URL,
        json={"new_phone": new_phone, "new_phone_code": new_code},
        headers={**creator.headers, "Step-Up-Code": current_code},
    )

    assert response.json()["waiting"]["without_current_number"] is False
    assert response.json()["waiting"]["takes_effect_at"] == stamp(
        clock.now + PHONE_CHANGE_WAIT
    )


def test_a_login_one_second_short_of_30_days_waits_one_second(
    client, sender, clock, creator
):
    creator.logged_in_at = clock.now - LOST_NUMBER_LOGIN + timedelta(seconds=1)

    response = lost(client, sender, creator.headers, unique_test_phone(), code="123456")

    assert_problem(response, 403, "login_too_recent")
    assert response.headers["Retry-After"] == "1"
    assert sender.sent == []


def test_a_login_exactly_30_days_old_may_ask(client, sender, clock, creator):
    creator.logged_in_at = clock.now - LOST_NUMBER_LOGIN

    assert lost(client, sender, creator.headers, unique_test_phone()).status_code == 202


def test_a_week_old_login_is_enough_with_both_numbers_but_not_without(
    client, sender, clock, creator
):
    creator.logged_in_at = clock.now - timedelta(days=8)

    response = lost(client, sender, creator.headers, unique_test_phone(), code="123456")

    assert_problem(response, 403, "login_too_recent")


def test_a_wrong_code_for_the_new_number_changes_nothing(client, db, sender, creator):
    new_phone = unique_test_phone()
    code = login_code(client, sender, new_phone)

    response = lost(
        client, sender, creator.headers, new_phone, code=f"{(int(code) + 1) % 10**6:06d}"
    )

    assert_problem(response, 400, "otp_invalid")
    assert waiting_row(db, creator) is None


def test_a_number_with_an_account_is_refused(client, db, sender, creator):
    taken = unique_test_phone()
    create_account(db, "brand", phone=taken)
    db.commit()

    assert_problem(lost(client, sender, creator.headers, taken), 409, "phone_in_use")


def test_your_own_number_and_admins_are_refused(client, db, sender, clock, creator):
    admin = User(create_account(db, "admin").id, "admin", clock)
    db.commit()

    own = lost(client, sender, creator.headers, phone_of(db, creator), code="123456")
    by_admin = lost(client, sender, admin.headers, unique_test_phone(), code="123456")

    assert_problem(own, 409, "phone_unchanged")
    assert_problem(by_admin, 403, "role_not_allowed")


def test_signed_out_nobody_may_ask(client):
    response = client.post(
        LOST_URL, json={"new_phone": "+919812300001", "new_phone_code": "123456"}
    )

    assert response.status_code == 401


# --- the wait and the change -----------------------------------------------------------


def test_a_lost_number_change_is_not_made_at_72_hours_only_at_seven_days(
    client, db, sender, clock, creator
):
    old_phone, new_phone = phone_of(db, creator), unique_test_phone()
    assert lost(client, sender, creator.headers, new_phone).status_code == 202

    clock.advance(PHONE_CHANGE_WAIT)
    at_72_hours = run_job(db, clock)
    clock.advance(
        PHONE_CHANGE_WAIT_WITHOUT_CURRENT - PHONE_CHANGE_WAIT - timedelta(seconds=1)
    )
    a_second_short = run_job(db, clock)
    after_72 = phone_of(db, creator)
    clock.advance(timedelta(seconds=1))
    at_seven_days = run_job(db, clock)

    assert (at_72_hours.made, a_second_short.made, at_seven_days.made) == (0, 0, 1)
    assert after_72 == old_phone
    assert phone_of(db, creator) == new_phone


def test_a_login_with_the_current_number_cancels_it_and_says_why(
    client, db, sender, clock, creator
):
    old_phone = phone_of(db, creator)
    assert lost(client, sender, creator.headers, unique_test_phone()).status_code == 202
    clock.advance(timedelta(days=1))

    logged_in = log_in(client, sender, old_phone)
    shown = client.get(URL, headers=creator.headers).json()
    attention = client.get(ATTENTION_URL, headers=creator.headers).json()
    run = run_job(db, clock)
    clock.advance(PHONE_CHANGE_WAIT_WITHOUT_CURRENT)
    later = run_job(db, clock)

    assert logged_in["account"]["id"] == str(creator.account_id)
    assert shown["waiting"] is None
    assert attention["counts"]["phone_change_pending"] == 0
    assert (run.voided, later.made) == (1, 0)
    assert phone_of(db, creator) == old_phone
    assert waiting_row(db, creator) is None
    [notice] = told(db, creator.account_id, "phone_change_cancelled")
    assert notice.details == {"reason": "logged_in_with_current_number"}


def test_refreshing_the_session_that_asked_does_not_cancel_it(client, db, sender, clock):
    phone = unique_test_phone()
    tokens = log_in(client, sender, phone)
    for _ in range(2):
        clock.advance(timedelta(days=16))
        tokens = client.post(
            REFRESH_URL, json={"refresh_token": tokens["refresh_token"]}
        ).json()
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    new_phone = unique_test_phone()
    assert lost(client, sender, headers, new_phone).status_code == 202

    clock.advance(timedelta(days=1))
    tokens = client.post(
        REFRESH_URL, json={"refresh_token": tokens["refresh_token"]}
    ).json()
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    shown = client.get(URL, headers=headers).json()
    clock.advance(PHONE_CHANGE_WAIT_WITHOUT_CURRENT)
    run = run_job(db, clock)

    assert shown["waiting"]["new_phone"] == new_phone
    assert (run.voided, run.made) == (0, 1)


def test_a_login_with_the_current_number_never_cancels_a_change_with_both(
    client, db, sender, clock, creator
):
    old_phone, new_phone = phone_of(db, creator), unique_test_phone()
    asked = client.post(
        STEP_UP_URL,
        json={"action": "change_phone", "new_phone": new_phone},
        headers=creator.headers,
    )
    assert asked.status_code == 202
    current_code = sender.last_code_for(old_phone)
    new_code = login_code(client, sender, new_phone)
    client.post(
        URL,
        json={"new_phone": new_phone, "new_phone_code": new_code},
        headers={**creator.headers, "Step-Up-Code": current_code},
    )
    clock.advance(timedelta(hours=1))

    log_in(client, sender, old_phone)
    clock.advance(PHONE_CHANGE_WAIT)
    run = run_job(db, clock)

    assert (run.voided, run.made) == (0, 1)
    assert phone_of(db, creator) == new_phone


def test_the_export_says_a_change_was_asked_without_the_current_number(
    client, db, sender, clock, creator
):
    assert lost(client, sender, creator.headers, unique_test_phone()).status_code == 202
    clock.advance(timedelta(minutes=10))

    [row] = download_export(client, creator.headers).json()["data"]["phone_change"]

    assert row["without_current_number"] is True
