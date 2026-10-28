"""A login at least a week old before a change a SIM swapper would want (D-109), through the API.

Changing the phone number, and replacing a UPI ID already in effect, are
refused from a login under 7 days old, before any code is sent or spent; a
first UPI ID, or confirming the one in effect, never is. The login's age is
the token's `auth_time`, kept through every refresh of that login.
"""

from collections.abc import Iterator
from datetime import timedelta

import pytest

from app.core.config import settings
from app.main import app
from app.modules.auth.login_age import ESTABLISHED_LOGIN
from app.modules.auth.sender import FakeOtpSender, get_otp_sender
from app.modules.auth.tokens import create_access_token
from app.modules.payment_status.upi_change_models import UPI_CHANGE_HOLD
from tests.deal_flow import User, creator_user
from tests.factories import unique_test_phone
from tests.step_up import STEP_UP_URL

PHONE_CHANGE_URL = "/api/v1/me/phone-change"
UPI_URL = "/api/v1/creators/me/upi"
OTP_REQUEST_URL = "/api/v1/auth/otp/request"
OTP_VERIFY_URL = "/api/v1/auth/otp/verify"
REFRESH_URL = "/api/v1/auth/refresh"
NOTICE = "upi-2026-10"
FIRST_ID = "meena.cooks@okhdfcbank"
OTHER_ID = "meena.new@okaxis"


@pytest.fixture(autouse=True)
def notice_ready(monkeypatch):
    monkeypatch.setattr(settings, "upi_notice_version", NOTICE)


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


def assert_problem(response, status: int, code: str) -> None:
    assert response.status_code == status, response.text
    assert response.json()["code"] == code


def ask(client, headers, action: str, **fields: str):
    return client.post(STEP_UP_URL, json={"action": action, **fields}, headers=headers)


def set_upi(client, sender, user: User, upi_id: str):
    """Ask for the code and set the ID, both with the user's login as it stands."""
    asked = ask(client, user.headers, "set_upi_id", upi_id=upi_id)
    if asked.status_code != 202:
        return asked
    return client.put(
        UPI_URL,
        json={"upi_id": upi_id, "consent": True, "notice_version": NOTICE},
        headers={**user.headers, "Step-Up-Code": sender.sent[-1].code},
    )


def in_effect(client, clock, sender, user: User, upi_id: str) -> None:
    assert set_upi(client, sender, user, upi_id).status_code == 200
    clock.advance(UPI_CHANGE_HOLD)


# --- the phone number --------------------------------------------------------------


def test_a_new_login_is_refused_a_phone_change_and_sent_no_code(
    client, sender, clock, creator
):
    creator.logged_in_at = clock.now

    asked = ask(client, creator.headers, "change_phone", new_phone=unique_test_phone())
    posted = client.post(
        PHONE_CHANGE_URL,
        json={"new_phone": unique_test_phone(), "new_phone_code": "123456"},
        headers={**creator.headers, "Step-Up-Code": "123456"},
    )

    assert_problem(asked, 403, "login_too_recent")
    assert asked.headers["Retry-After"] == str(int(ESTABLISHED_LOGIN.total_seconds()))
    assert_problem(posted, 403, "login_too_recent")
    assert sender.sent == []
    assert client.get(PHONE_CHANGE_URL, headers=creator.headers).json()["waiting"] is None


def test_a_login_one_second_short_of_a_week_waits_one_second(client, clock, creator):
    creator.logged_in_at = clock.now - ESTABLISHED_LOGIN + timedelta(seconds=1)

    asked = ask(client, creator.headers, "change_phone", new_phone=unique_test_phone())

    assert_problem(asked, 403, "login_too_recent")
    assert asked.headers["Retry-After"] == "1"


def test_a_login_exactly_a_week_old_may_ask(client, sender, clock, creator):
    creator.logged_in_at = clock.now - ESTABLISHED_LOGIN

    asked = ask(client, creator.headers, "change_phone", new_phone=unique_test_phone())

    assert asked.status_code == 202, asked.text


def test_a_token_that_does_not_say_when_its_login_was_counts_as_new(
    client, sender, clock, creator
):
    token, _ = create_access_token(creator.account_id, "creator", clock.now)

    asked = ask(
        client,
        {"Authorization": f"Bearer {token}"},
        "change_phone",
        new_phone=unique_test_phone(),
    )

    assert_problem(asked, 403, "login_too_recent")


def test_a_real_login_keeps_its_age_through_every_refresh(client, db, sender, clock):
    phone = unique_test_phone()
    client.post(OTP_REQUEST_URL, json={"phone": phone})
    tokens = client.post(
        OTP_VERIFY_URL,
        json={"phone": phone, "code": sender.last_code_for(phone), "role": "creator"},
    ).json()

    def ask_with(access_token: str):
        return ask(
            client,
            {"Authorization": f"Bearer {access_token}"},
            "change_phone",
            new_phone=unique_test_phone(),
        )

    refused = ask_with(tokens["access_token"])
    for _ in range(7):
        clock.advance(timedelta(days=1))
        tokens = client.post(
            REFRESH_URL, json={"refresh_token": tokens["refresh_token"]}
        ).json()
    allowed = ask_with(tokens["access_token"])

    assert_problem(refused, 403, "login_too_recent")
    assert allowed.status_code == 202, allowed.text


def test_refreshing_does_not_make_a_new_login_look_old(client, db, sender, clock):
    phone = unique_test_phone()
    client.post(OTP_REQUEST_URL, json={"phone": phone})
    tokens = client.post(
        OTP_VERIFY_URL,
        json={"phone": phone, "code": sender.last_code_for(phone), "role": "creator"},
    ).json()
    clock.advance(timedelta(days=6, hours=23))
    tokens = client.post(
        REFRESH_URL, json={"refresh_token": tokens["refresh_token"]}
    ).json()

    asked = ask(
        client,
        {"Authorization": f"Bearer {tokens['access_token']}"},
        "change_phone",
        new_phone=unique_test_phone(),
    )

    assert_problem(asked, 403, "login_too_recent")
    assert asked.headers["Retry-After"] == str(60 * 60)


# --- the UPI ID --------------------------------------------------------------------


def test_a_new_login_may_give_a_first_upi_id(client, sender, clock, creator):
    creator.logged_in_at = clock.now

    assert set_upi(client, sender, creator, FIRST_ID).status_code == 200


def test_a_new_login_may_replace_a_first_id_still_waiting(client, sender, clock, creator):
    creator.logged_in_at = clock.now
    assert set_upi(client, sender, creator, FIRST_ID).status_code == 200
    clock.advance(timedelta(minutes=5))

    assert set_upi(client, sender, creator, OTHER_ID).status_code == 200


def test_a_new_login_is_refused_replacing_an_id_in_effect_and_sent_no_code(
    client, sender, clock, creator
):
    in_effect(client, clock, sender, creator, FIRST_ID)
    sent_before = len(sender.sent)
    creator.logged_in_at = clock.now

    asked = ask(client, creator.headers, "set_upi_id", upi_id=OTHER_ID)

    assert_problem(asked, 403, "login_too_recent")
    assert len(sender.sent) == sent_before


def test_a_new_login_cannot_spend_a_code_on_replacing_an_id_in_effect(
    client, sender, clock, creator
):
    in_effect(client, clock, sender, creator, FIRST_ID)
    asked = ask(client, creator.headers, "set_upi_id", upi_id=OTHER_ID)
    assert asked.status_code == 202
    code = sender.sent[-1].code
    body = {"upi_id": OTHER_ID, "consent": True, "notice_version": NOTICE}
    creator.logged_in_at = clock.now

    refused = client.put(
        UPI_URL, json=body, headers={**creator.headers, "Step-Up-Code": code}
    )
    creator.logged_in_at = None
    accepted = client.put(
        UPI_URL, json=body, headers={**creator.headers, "Step-Up-Code": code}
    )

    assert_problem(refused, 403, "login_too_recent")
    # The code was not spent by the refusal.
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["waiting"]["upi_id"] == OTHER_ID


def test_a_new_login_may_confirm_the_id_already_in_effect(client, sender, clock, creator):
    in_effect(client, clock, sender, creator, FIRST_ID)
    creator.logged_in_at = clock.now

    assert set_upi(client, sender, creator, FIRST_ID).status_code == 200
