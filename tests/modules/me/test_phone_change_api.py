"""Changing the phone number you log in with (item 80, D-108), through the API.

A code from each number; a 72-hour wait the owner can cancel with no code;
the old number still logging in, and the new one refused a new account,
meanwhile; then the job moving the account, ending every session and
letting the old number go. The table's own rules are in
tests/modules/auth/test_account_phone_change_model.py, two accounts racing
for one number in test_phone_change_concurrency.py.
"""

from collections.abc import Iterator
from contextlib import nullcontext
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.core.clock import india_date
from app.main import app
from app.modules.auth import step_up_service
from app.modules.auth.exceptions import RoleNotAllowed
from app.modules.auth.models.account import Account
from app.modules.auth.models.account_phone_change import (
    PHONE_CHANGE_WAIT,
    AccountPhoneChange,
)
from app.modules.auth.models.otp_challenge import OtpChallenge
from app.modules.auth.models.step_up_challenge import StepUpChallenge
from app.modules.auth.sender import FakeOtpSender, get_otp_sender
from app.modules.me import phone_change_service as service
from app.modules.me.phone_change_router import CHANGE_LIMIT
from app.modules.notifications.models import Notification
from tests.deal_flow import User, brand_user, creator_user
from tests.factories import create_account, unique_test_phone
from tests.step_up import STEP_UP_URL, download_export

URL = "/api/v1/me/phone-change"
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
    # Committed, so a refusal's rollback inside a request cannot undo it.
    db.commit()
    return user


@pytest.fixture
def brand(db, clock) -> User:
    user = brand_user(db, clock)
    db.commit()
    return user


def phone_of(db, user: User) -> str:
    return db.scalars(
        select(Account.phone)
        .where(Account.id == user.account_id)
        .execution_options(populate_existing=True)
    ).one()


def ask_step_up(client, user: User, new_phone: str):
    return client.post(
        STEP_UP_URL,
        json={"action": "change_phone", "new_phone": new_phone},
        headers=user.headers,
    )


def step_up_code(client, db, sender, user: User, new_phone: str) -> str:
    response = ask_step_up(client, user, new_phone)
    assert response.status_code == 202, response.text
    code = sender.last_code_for(phone_of(db, user))
    assert code is not None
    return code


def login_code(client, sender, phone: str) -> str:
    response = client.post(OTP_REQUEST_URL, json={"phone": phone})
    assert response.status_code == 202, response.text
    code = sender.last_code_for(phone)
    assert code is not None
    return code


def post_change(client, user: User, new_phone: str, new_code: str, current_code: str):
    return client.post(
        URL,
        json={"new_phone": new_phone, "new_phone_code": new_code},
        headers={**user.headers, "Step-Up-Code": current_code},
    )


def change(client, db, sender, user: User, new_phone: str):
    """Ask for both codes, then the change, as an app would."""
    current_code = step_up_code(client, db, sender, user, new_phone)
    new_code = login_code(client, sender, new_phone)
    return post_change(client, user, new_phone, new_code, current_code)


def log_in(client, sender, phone: str, role: str):
    code = login_code(client, sender, phone)
    return client.post(OTP_VERIFY_URL, json={"phone": phone, "code": code, "role": role})


def run_job(db, clock) -> service.ChangeRun:
    return service.run_changes(lambda: nullcontext(db), clock.now)


def wrong(code: str) -> str:
    return f"{(int(code) + 1) % 1_000_000:06d}"


def assert_problem(response, status: int, code: str) -> None:
    assert response.status_code == status, response.text
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["code"] == code


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


def latest_login_code(db, phone: str) -> OtpChallenge:
    return db.scalars(
        select(OtpChallenge)
        .where(OtpChallenge.phone == phone)
        .order_by(OtpChallenge.created_at.desc())
        .limit(1)
        .execution_options(populate_existing=True)
    ).one()


# --- asking ----------------------------------------------------------------------------


def test_with_a_code_from_each_number_the_change_waits_72_hours(
    client, db, sender, clock, creator
):
    old_phone, new_phone = phone_of(db, creator), unique_test_phone()

    response = change(client, db, sender, creator, new_phone)

    assert response.status_code == 202, response.text
    takes_effect_at = clock.now + PHONE_CHANGE_WAIT
    assert response.json() == {
        "phone": old_phone,
        "waiting": {
            "new_phone": new_phone,
            "requested_at": clock.now.isoformat().replace("+00:00", "Z"),
            "takes_effect_at": takes_effect_at.isoformat().replace("+00:00", "Z"),
            "without_current_number": False,
        },
    }
    assert client.get(URL, headers=creator.headers).json() == response.json()
    assert phone_of(db, creator) == old_phone
    [notice] = told(db, creator.account_id, "phone_change_requested")
    assert notice.details == {"takes_effect_at": takes_effect_at.isoformat()}


def test_nothing_waiting_reads_as_null(client, creator):
    response = client.get(URL, headers=creator.headers)

    assert response.status_code == 200
    assert response.json()["waiting"] is None


def test_the_new_numbers_code_is_used_up_and_logs_nobody_in(client, db, sender, creator):
    new_phone = unique_test_phone()
    current_code = step_up_code(client, db, sender, creator, new_phone)
    new_code = login_code(client, sender, new_phone)
    assert (
        post_change(client, creator, new_phone, new_code, current_code).status_code == 202
    )

    login = client.post(
        OTP_VERIFY_URL, json={"phone": new_phone, "code": new_code, "role": "creator"}
    )

    assert_problem(login, 400, "otp_invalid")


def test_the_current_numbers_code_works_once(client, db, sender, clock, creator):
    new_phone = unique_test_phone()
    current_code = step_up_code(client, db, sender, creator, new_phone)
    first = login_code(client, sender, new_phone)
    assert post_change(client, creator, new_phone, first, current_code).status_code == 202
    clock.advance(timedelta(minutes=1))
    second = login_code(client, sender, new_phone)

    again = post_change(client, creator, new_phone, second, current_code)

    assert_problem(again, 400, "step_up_code_invalid")


def test_without_a_code_from_the_current_number_nothing_changes(
    client, db, sender, creator
):
    new_phone = unique_test_phone()
    new_code = login_code(client, sender, new_phone)

    response = client.post(
        URL,
        json={"new_phone": new_phone, "new_phone_code": new_code},
        headers=creator.headers,
    )

    assert_problem(response, 401, "step_up_required")
    assert "insufficient_user_authentication" in response.headers["WWW-Authenticate"]
    assert waiting_row(db, creator) is None
    assert latest_login_code(db, new_phone).consumed_at is None


def test_without_a_code_from_the_current_number_the_new_ones_is_not_tried(
    client, db, sender, creator
):
    new_phone = unique_test_phone()
    new_code = login_code(client, sender, new_phone)

    response = client.post(
        URL,
        json={"new_phone": new_phone, "new_phone_code": wrong(new_code)},
        headers=creator.headers,
    )

    assert_problem(response, 401, "step_up_required")
    assert latest_login_code(db, new_phone).attempts == 0


def test_a_code_asked_for_another_number_cannot_move_it_here(client, db, sender, creator):
    new_phone, other_phone = unique_test_phone(), unique_test_phone()
    current_code = step_up_code(client, db, sender, creator, other_phone)
    new_code = login_code(client, sender, new_phone)

    response = post_change(client, creator, new_phone, new_code, current_code)

    assert_problem(response, 400, "step_up_code_invalid")
    assert waiting_row(db, creator) is None


def test_the_code_is_bound_to_the_new_number_by_a_keyed_hash_only(
    client, db, sender, creator
):
    new_phone = unique_test_phone()

    step_up_code(client, db, sender, creator, new_phone)

    [row] = db.scalars(
        select(StepUpChallenge).where(StepUpChallenge.account_id == creator.account_id)
    ).all()
    assert row.action == "change_phone"
    assert row.value_hash == step_up_service.value_hash("change_phone", new_phone)
    assert new_phone not in (row.value_hash, row.code_hash)


def test_a_wrong_code_for_the_new_number_spends_neither_code(client, db, sender, creator):
    new_phone = unique_test_phone()
    current_code = step_up_code(client, db, sender, creator, new_phone)
    new_code = login_code(client, sender, new_phone)

    refused = post_change(client, creator, new_phone, wrong(new_code), current_code)
    accepted = post_change(client, creator, new_phone, new_code, current_code)

    assert_problem(refused, 400, "otp_invalid")
    assert accepted.status_code == 202, accepted.text


def test_a_wrong_code_from_the_current_number_spends_only_its_own_try(
    client, db, sender, creator
):
    new_phone = unique_test_phone()
    current_code = step_up_code(client, db, sender, creator, new_phone)
    new_code = login_code(client, sender, new_phone)

    refused = post_change(client, creator, new_phone, new_code, wrong(current_code))
    accepted = post_change(client, creator, new_phone, new_code, current_code)

    assert_problem(refused, 400, "step_up_code_invalid")
    assert accepted.status_code == 202, accepted.text


@pytest.mark.parametrize(
    "body",
    [
        {"new_phone": "12345", "new_phone_code": "123456"},
        {"new_phone": "+919812300001", "new_phone_code": "12ab56"},
        {"new_phone": "+919812300001"},
        {"new_phone": "+919812300001", "new_phone_code": "123456", "role": "admin"},
    ],
)
def test_a_malformed_request_is_refused(client, creator, body):
    response = client.post(
        URL, json=body, headers={**creator.headers, "Step-Up-Code": "123456"}
    )

    assert response.status_code == 422, response.text


def test_signed_out_nobody_may_read_ask_or_cancel(client):
    assert client.get(URL).status_code == 401
    assert (
        client.post(
            URL, json={"new_phone": "+919812300001", "new_phone_code": "123456"}
        ).status_code
        == 401
    )
    assert client.delete(URL).status_code == 401


def test_your_own_number_is_refused_before_any_code_is_sent(client, db, sender, creator):
    own = phone_of(db, creator)

    asked = ask_step_up(client, creator, own)
    posted = post_change(client, creator, own, "123456", "123456")

    assert_problem(asked, 409, "phone_unchanged")
    assert_problem(posted, 409, "phone_unchanged")
    assert sender.sent == []


def test_a_number_with_an_account_is_refused_only_to_its_holder(
    client, db, sender, creator
):
    taken = unique_test_phone()
    create_account(db, "brand", phone=taken)
    db.commit()
    current_code = step_up_code(client, db, sender, creator, taken)
    new_code = login_code(client, sender, taken)

    guessed = post_change(client, creator, taken, wrong(new_code), current_code)
    held = post_change(client, creator, taken, new_code, current_code)

    # Without the number's code, it reads as a wrong code like any other.
    assert_problem(guessed, 400, "otp_invalid")
    assert_problem(held, 409, "phone_in_use")
    assert waiting_row(db, creator) is None
    # Neither code was spent on a change that was not made.
    assert latest_login_code(db, taken).consumed_at is None
    assert post_change(client, creator, taken, new_code, current_code).status_code == 409


def test_a_number_another_account_waits_on_is_refused(
    client, db, sender, clock, creator, brand
):
    new_phone = unique_test_phone()
    assert change(client, db, sender, brand, new_phone).status_code == 202
    clock.advance(timedelta(minutes=1))

    response = change(client, db, sender, creator, new_phone)

    assert_problem(response, 409, "phone_in_use")
    assert waiting_row(db, creator) is None


def test_an_admins_number_is_changed_only_by_the_script(client, db, sender, clock):
    admin = User(create_account(db, "admin").id, "admin", clock)
    db.commit()
    new_phone = unique_test_phone()

    asked = ask_step_up(client, admin, new_phone)
    posted = post_change(client, admin, new_phone, "123456", "123456")

    assert_problem(asked, 403, "role_not_allowed")
    assert_problem(posted, 403, "role_not_allowed")
    assert sender.sent == []


def test_the_step_up_service_itself_sends_an_admin_no_phone_change_code(db, clock):
    """Its own role table, not only the route's check, refuses an admin."""
    admin = create_account(db, "admin")

    with pytest.raises(RoleNotAllowed):
        step_up_service.request_code(
            db, admin, "change_phone", unique_test_phone(), clock.now
        )


def test_asking_again_replaces_the_change_and_starts_its_wait_again(
    client, db, sender, clock, creator
):
    first, second = unique_test_phone(), unique_test_phone()
    assert change(client, db, sender, creator, first).status_code == 202
    clock.advance(timedelta(hours=10))

    response = change(client, db, sender, creator, second)

    assert response.status_code == 202, response.text
    row = waiting_row(db, creator)
    assert row is not None
    assert (row.new_phone, row.takes_effect_at) == (
        second,
        clock.now + PHONE_CHANGE_WAIT,
    )
    assert len(told(db, creator.account_id, "phone_change_requested")) == 2


def test_a_change_past_its_72_hours_cannot_be_replaced(
    client, db, sender, clock, creator
):
    assert change(client, db, sender, creator, unique_test_phone()).status_code == 202
    clock.advance(PHONE_CHANGE_WAIT)

    response = change(client, db, sender, creator, unique_test_phone())

    assert_problem(response, 409, "phone_change_taking_effect")
    assert response.headers["Retry-After"] == "60"


def test_asking_is_limited_per_account(client, creator):
    allowed = int(CHANGE_LIMIT.split(" ")[0])
    body = {"new_phone": "+919812300001", "new_phone_code": "123456"}

    answers = [
        client.post(URL, json=body, headers=creator.headers).status_code
        for _ in range(allowed + 1)
    ]

    assert answers == [401] * allowed + [429]


# --- cancelling ------------------------------------------------------------------------


def test_cancelling_needs_no_code_and_keeps_the_number(
    client, db, sender, clock, creator
):
    old_phone = phone_of(db, creator)
    assert change(client, db, sender, creator, unique_test_phone()).status_code == 202
    clock.advance(timedelta(hours=1))

    response = client.delete(URL, headers=creator.headers)

    assert response.status_code == 204, response.text
    assert waiting_row(db, creator) is None
    assert client.get(URL, headers=creator.headers).json() == {
        "phone": old_phone,
        "waiting": None,
    }
    assert len(told(db, creator.account_id, "phone_change_cancelled")) == 1


def test_cancelling_with_nothing_waiting_is_fine_and_tells_nobody(client, db, creator):
    first = client.delete(URL, headers=creator.headers)
    second = client.delete(URL, headers=creator.headers)

    assert (first.status_code, second.status_code) == (204, 204)
    assert told(db, creator.account_id, "phone_change_cancelled") == []


def test_a_change_can_be_cancelled_until_its_last_second(
    client, db, sender, clock, creator
):
    assert change(client, db, sender, creator, unique_test_phone()).status_code == 202
    clock.advance(PHONE_CHANGE_WAIT - timedelta(seconds=1))

    assert client.delete(URL, headers=creator.headers).status_code == 204


def test_from_its_72nd_hour_a_change_cannot_be_cancelled(
    client, db, sender, clock, creator
):
    assert change(client, db, sender, creator, unique_test_phone()).status_code == 202
    clock.advance(PHONE_CHANGE_WAIT)

    response = client.delete(URL, headers=creator.headers)

    assert_problem(response, 409, "phone_change_taking_effect")
    assert response.headers["Retry-After"] == "60"
    assert waiting_row(db, creator) is not None


# --- logging in while it waits ---------------------------------------------------------


def test_the_old_number_still_logs_in_while_it_waits(client, db, sender, creator):
    old_phone = phone_of(db, creator)
    assert change(client, db, sender, creator, unique_test_phone()).status_code == 202

    response = log_in(client, sender, old_phone, "creator")

    assert response.status_code == 200, response.text
    assert response.json()["account"]["id"] == str(creator.account_id)


def test_the_new_number_cannot_make_an_account_while_it_waits(
    client, db, sender, clock, creator
):
    new_phone = unique_test_phone()
    assert change(client, db, sender, creator, new_phone).status_code == 202
    clock.advance(timedelta(minutes=1))
    code = login_code(client, sender, new_phone)
    body = {"phone": new_phone, "code": code, "role": "brand"}

    refused = client.post(OTP_VERIFY_URL, json=body)
    assert client.delete(URL, headers=creator.headers).status_code == 204
    after_cancel = client.post(OTP_VERIFY_URL, json=body)

    assert_problem(refused, 409, "phone_change_waiting")
    # The code stayed usable: once the change is cancelled the number is free.
    assert after_cancel.status_code == 200, after_cancel.text
    assert after_cancel.json()["account"]["is_new"] is True


# --- the change being made -------------------------------------------------------------


def test_nothing_is_made_before_72_hours(client, db, sender, clock, creator):
    old_phone = phone_of(db, creator)
    assert change(client, db, sender, creator, unique_test_phone()).status_code == 202
    clock.advance(PHONE_CHANGE_WAIT - timedelta(seconds=1))

    run = run_job(db, clock)

    assert (run.due, run.made) == (0, 0)
    assert phone_of(db, creator) == old_phone


def test_at_72_hours_the_account_moves_and_every_session_ends(
    client, db, sender, clock, creator
):
    old_phone, new_phone = phone_of(db, creator), unique_test_phone()
    session = log_in(client, sender, old_phone, "creator").json()
    assert change(client, db, sender, creator, new_phone).status_code == 202
    clock.advance(PHONE_CHANGE_WAIT)

    run = run_job(db, clock)

    assert (run.due, run.made, run.dropped) == (1, 1, 0)
    assert phone_of(db, creator) == new_phone
    assert waiting_row(db, creator) is None
    refreshed = client.post(REFRESH_URL, json={"refresh_token": session["refresh_token"]})
    assert_problem(refreshed, 401, "invalid_token")
    [notice] = told(db, creator.account_id, "phone_changed")
    assert notice.details == {"sessions_ended": 1}
    assert client.get(URL, headers=creator.headers).json() == {
        "phone": new_phone,
        "waiting": None,
    }


def test_afterwards_the_new_number_logs_in_and_the_old_one_is_let_go(
    client, db, sender, clock, creator
):
    old_phone, new_phone = phone_of(db, creator), unique_test_phone()
    assert change(client, db, sender, creator, new_phone).status_code == 202
    clock.advance(PHONE_CHANGE_WAIT)
    run_job(db, clock)
    clock.advance(timedelta(minutes=1))

    with_new = log_in(client, sender, new_phone, "creator")
    with_old = log_in(client, sender, old_phone, "creator")

    assert with_new.json()["account"] == {
        "id": str(creator.account_id),
        "role": "creator",
        "is_new": False,
    }
    # Whoever is given the old number next finds a new account, never this one.
    assert with_old.json()["account"]["is_new"] is True
    assert with_old.json()["account"]["id"] != str(creator.account_id)


def test_running_the_job_twice_makes_the_change_once(client, db, sender, clock, creator):
    assert change(client, db, sender, creator, unique_test_phone()).status_code == 202
    clock.advance(PHONE_CHANGE_WAIT)
    change_id = waiting_row(db, creator).id  # type: ignore[union-attr]

    first, second = run_job(db, clock), run_job(db, clock)

    assert (first.made, second.due) == (1, 0)
    assert service.make_change(db, change_id, clock.now) is None
    assert len(told(db, creator.account_id, "phone_changed")) == 1


def test_a_change_not_yet_due_is_left_alone(client, db, sender, clock, creator):
    old_phone = phone_of(db, creator)
    assert change(client, db, sender, creator, unique_test_phone()).status_code == 202
    row = waiting_row(db, creator)
    assert row is not None

    assert service.make_change(db, row.id, clock.now) is None
    assert phone_of(db, creator) == old_phone
    assert waiting_row(db, creator) is not None


def test_a_number_taken_meanwhile_drops_the_change_and_says_so(
    client, db, sender, clock, creator
):
    old_phone, new_phone = phone_of(db, creator), unique_test_phone()
    assert change(client, db, sender, creator, new_phone).status_code == 202
    # As scripts/make_admin.py could, which login's refusal does not cover.
    create_account(db, "admin", phone=new_phone)
    db.commit()
    clock.advance(PHONE_CHANGE_WAIT)

    run = run_job(db, clock)

    assert (run.made, run.dropped) == (0, 1)
    assert phone_of(db, creator) == old_phone
    assert waiting_row(db, creator) is None
    assert len(told(db, creator.account_id, "phone_change_failed")) == 1


# --- what the owner sees ---------------------------------------------------------------


@pytest.mark.parametrize("role", ["brand", "creator"])
def test_a_waiting_change_is_first_on_the_attention_list(
    client, db, sender, clock, role, request
):
    user: User = request.getfixturevalue(role)
    takes_effect_at = clock.now + PHONE_CHANGE_WAIT
    assert change(client, db, sender, user, unique_test_phone()).status_code == 202

    attention = client.get(ATTENTION_URL, headers=user.headers).json()
    clock.advance(PHONE_CHANGE_WAIT)
    after = client.get(ATTENTION_URL, headers=user.headers).json()

    first = attention["items"][0]
    assert first["kind"] == "phone_change_pending"
    assert first["due_on"] == india_date(takes_effect_at).isoformat()
    assert attention["counts"]["phone_change_pending"] == 1
    assert after["counts"]["phone_change_pending"] == 0


def test_a_cancelled_change_leaves_the_attention_list(client, db, sender, creator):
    assert change(client, db, sender, creator, unique_test_phone()).status_code == 202
    client.delete(URL, headers=creator.headers)

    attention = client.get(ATTENTION_URL, headers=creator.headers).json()

    assert attention["counts"]["phone_change_pending"] == 0


def test_the_export_holds_a_waiting_change(client, db, sender, clock, creator):
    new_phone = unique_test_phone()
    assert change(client, db, sender, creator, new_phone).status_code == 202
    clock.advance(timedelta(minutes=10))

    data = download_export(client, creator.headers).json()["data"]

    [row] = data["phone_change"]
    assert row["new_phone"] == new_phone
    assert set(row) == {
        "new_phone",
        "requested_at",
        "takes_effect_at",
        "without_current_number",
        "created_at",
        "updated_at",
    }
