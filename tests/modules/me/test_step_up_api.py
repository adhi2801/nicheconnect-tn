"""The second check before a risky change (item 82, D-107), through the API.

Asking for a code; the code allowing exactly one change, once, for 5
minutes; the phone's caps shared with login codes; the export and logging
out everywhere refused without one; admins proving it with their
authenticator. The UPI ID's own rules, the 24-hour wait among them, are in
tests/modules/payment_status/test_upi_hold_api.py.
"""

from collections.abc import Iterator
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.main import app
from app.modules.auth import second_factor, second_factor_secrets, step_up_service
from app.modules.auth.models.account import Account
from app.modules.auth.models.auth_session import AuthSession
from app.modules.auth.models.step_up_challenge import StepUpChallenge
from app.modules.auth.models.totp_factor import MAX_CONSECUTIVE_FAILURES, TotpFactor
from app.modules.auth.sender import FakeOtpSender, get_otp_sender
from app.modules.me.step_up_router import STEP_UP_LIMIT
from app.modules.notifications.models import Notification
from tests.deal_flow import Clock, User, brand_user, creator_user
from tests.factories import build_auth_session, create_account
from tests.step_up import EXPORT_URL, LOGOUT_ALL_URL, STEP_UP_URL, download_export

UPI_ID = "meena.cooks@okhdfcbank"
OTP_REQUEST_URL = "/api/v1/auth/otp/request"
OTP_VERIFY_URL = "/api/v1/auth/otp/verify"


@pytest.fixture
def sender(client) -> Iterator[FakeOtpSender]:
    fake = FakeOtpSender()
    app.dependency_overrides[get_otp_sender] = lambda: fake
    yield fake
    app.dependency_overrides.pop(get_otp_sender, None)


@pytest.fixture
def creator(db, clock) -> User:
    return creator_user(db, clock)


@pytest.fixture
def brand(db, clock) -> User:
    return brand_user(db, clock)


def phone_of(db, user: User) -> str:
    return db.get_one(Account, user.account_id).phone


def ask(client, user: User, action: str, **fields: object):
    return client.post(
        STEP_UP_URL, json={"action": action, **fields}, headers=user.headers
    )


def code_for(client, db, sender, user: User, action: str, **fields: object) -> str:
    response = ask(client, user, action, **fields)
    assert response.status_code == 202, response.text
    code = sender.last_code_for(phone_of(db, user))
    assert code is not None
    return code


def with_header(user: User, code: str) -> dict[str, str]:
    return {**user.headers, "Step-Up-Code": code}


def wrong(code: str) -> str:
    return f"{(int(code) + 1) % 1_000_000:06d}"


def assert_problem(response, status: int, code: str) -> None:
    assert response.status_code == status, response.text
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["code"] == code


def told(db, user: User, kind: str) -> list[Notification]:
    return list(
        db.scalars(
            select(Notification).where(
                Notification.account_id == user.account_id,
                Notification.notification_type == kind,
            )
        ).all()
    )


# --- asking for a code --------------------------------------------------------------------


def test_a_code_is_sent_to_the_phone_for_one_change(client, db, sender, creator):
    response = ask(client, creator, "download_export")

    assert response.status_code == 202, response.text
    assert response.json() == {
        "action": "download_export",
        "method": "phone_code",
        "expires_in_seconds": 300,
    }
    [sent] = sender.sent
    assert sent.phone == phone_of(db, creator)
    [row] = db.scalars(
        select(StepUpChallenge).where(StepUpChallenge.account_id == creator.account_id)
    ).all()
    assert row.action == "download_export"
    assert sent.code not in (row.code_hash, row.value_hash)


def test_the_new_upi_id_is_kept_only_as_a_keyed_hash(client, db, sender, creator):
    ask(client, creator, "set_upi_id", upi_id="Meena.Cooks@OKHDFCBANK")

    row = db.scalars(
        select(StepUpChallenge).where(StepUpChallenge.account_id == creator.account_id)
    ).one()
    # Bound to the one spelling that would be stored.
    assert row.value_hash == step_up_service.value_hash("set_upi_id", UPI_ID)
    assert UPI_ID not in (row.value_hash, row.code_hash, row.action)


def test_only_a_creator_asks_to_set_a_upi_id(client, db, sender, brand, clock):
    admin = User(create_account(db, "admin").id, "admin", clock)

    assert_problem(
        ask(client, brand, "set_upi_id", upi_id=UPI_ID), 403, "role_not_allowed"
    )
    assert_problem(
        ask(client, admin, "set_upi_id", upi_id=UPI_ID), 403, "role_not_allowed"
    )
    assert sender.sent == []


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"action": "fly"},
        {"action": "set_upi_id"},
        {"action": "set_upi_id", "upi_id": "9876543210@ybl"},
        {"action": "set_upi_id", "upi_id": "meena"},
        {"action": "download_export", "upi_id": UPI_ID},
        {"action": "log_out_everywhere", "note": "hi"},
    ],
    ids=[
        "no action",
        "unknown action",
        "upi without an id",
        "phone-number upi",
        "not a upi id",
        "export with a value",
        "unknown field",
    ],
)
def test_a_request_that_is_not_one_change_is_refused(client, sender, creator, body):
    response = client.post(STEP_UP_URL, json=body, headers=creator.headers)

    assert response.status_code == 422
    assert sender.sent == []


def test_asking_needs_a_login(client, sender):
    assert_problem(
        client.post(STEP_UP_URL, json={"action": "download_export"}), 401, "invalid_token"
    )


def test_asking_is_rate_limited(client, sender, creator):
    allowed = int(STEP_UP_LIMIT.split()[0])
    answers = [
        ask(client, creator, "log_out_everywhere").status_code for _ in range(allowed + 1)
    ]

    assert answers[:allowed] == [202] * allowed
    assert answers[allowed] == 429


def test_login_codes_and_step_up_codes_share_the_phones_send_cap(
    client, db, sender, creator
):
    """Three codes in 10 minutes per phone, whichever route asked."""
    phone = phone_of(db, creator)
    for _ in range(2):
        assert client.post(OTP_REQUEST_URL, json={"phone": phone}).status_code == 202
    assert ask(client, creator, "download_export").status_code == 202

    assert_problem(
        client.post(OTP_REQUEST_URL, json={"phone": phone}), 429, "otp_send_limit_reached"
    )
    assert_problem(ask(client, creator, "download_export"), 429, "otp_send_limit_reached")


def test_wrong_step_up_codes_use_up_the_phones_guesses(
    client, db, sender, clock, creator
):
    """Ten wrong tries per phone in 10 minutes, across login and step-up codes."""
    for _ in range(2):
        code = code_for(client, db, sender, creator, "log_out_everywhere")
        for _ in range(5):
            response = client.post(
                LOGOUT_ALL_URL, headers=with_header(creator, wrong(code))
            )
            assert_problem(response, 400, "step_up_code_invalid")
        clock.advance(timedelta(seconds=1))

    phone = phone_of(db, creator)
    assert client.post(OTP_REQUEST_URL, json={"phone": phone}).status_code == 202
    response = client.post(
        OTP_VERIFY_URL,
        json={"phone": phone, "code": sender.last_code_for(phone), "role": "creator"},
    )

    assert_problem(response, 429, "otp_verify_limit_reached")


def test_after_ten_wrong_tries_even_the_right_code_waits(
    client, db, sender, clock, creator
):
    """The phone's guess cap holds for the step-up check itself, not only login."""
    for _ in range(2):
        code = code_for(client, db, sender, creator, "log_out_everywhere")
        for _ in range(5):
            client.post(LOGOUT_ALL_URL, headers=with_header(creator, wrong(code)))
        clock.advance(timedelta(seconds=1))
    fresh = code_for(client, db, sender, creator, "log_out_everywhere")

    response = client.post(LOGOUT_ALL_URL, headers=with_header(creator, fresh))

    assert_problem(response, 429, "otp_verify_limit_reached")
    assert int(response.headers["retry-after"]) > 0


# --- the code allows one change, once -----------------------------------------------------


def test_without_a_code_the_change_is_refused_with_the_rfc_9470_challenge(
    client, creator
):
    response = client.post(EXPORT_URL, headers=creator.headers)

    assert_problem(response, 401, "step_up_required")
    challenge = response.headers["www-authenticate"]
    assert challenge.startswith('Bearer error="insufficient_user_authentication"')


def test_the_right_code_allows_it(client, db, sender, creator):
    code = code_for(client, db, sender, creator, "download_export")

    assert client.post(EXPORT_URL, headers=with_header(creator, code)).status_code == 202


def test_a_wrong_code_is_refused_and_the_right_one_still_works(
    client, db, sender, creator
):
    code = code_for(client, db, sender, creator, "download_export")

    assert_problem(
        client.post(EXPORT_URL, headers=with_header(creator, wrong(code))),
        400,
        "step_up_code_invalid",
    )
    assert client.post(EXPORT_URL, headers=with_header(creator, code)).status_code == 202


def test_a_code_works_once(client, db, sender, creator):
    code = code_for(client, db, sender, creator, "log_out_everywhere")
    assert (
        client.post(LOGOUT_ALL_URL, headers=with_header(creator, code)).status_code == 200
    )

    assert_problem(
        client.post(LOGOUT_ALL_URL, headers=with_header(creator, code)),
        400,
        "step_up_code_invalid",
    )


def test_a_code_lasts_five_minutes(client, db, sender, clock, creator):
    code = code_for(client, db, sender, creator, "log_out_everywhere")
    clock.advance(timedelta(minutes=5))

    assert_problem(
        client.post(LOGOUT_ALL_URL, headers=with_header(creator, code)),
        400,
        "step_up_code_invalid",
    )


def test_a_code_works_until_its_last_second(client, db, sender, clock, creator):
    code = code_for(client, db, sender, creator, "log_out_everywhere")
    clock.advance(timedelta(minutes=5) - timedelta(seconds=1))

    assert (
        client.post(LOGOUT_ALL_URL, headers=with_header(creator, code)).status_code == 200
    )


def test_a_code_for_one_change_cannot_make_another(client, db, sender, creator):
    for_logout = code_for(client, db, sender, creator, "log_out_everywhere")
    for_export = code_for(client, db, sender, creator, "download_export")

    assert_problem(
        client.post(EXPORT_URL, headers=with_header(creator, for_logout)),
        400,
        "step_up_code_invalid",
    )
    assert_problem(
        client.post(LOGOUT_ALL_URL, headers=with_header(creator, for_export)),
        400,
        "step_up_code_invalid",
    )


def test_only_the_newest_code_counts(client, db, sender, clock, creator):
    first = code_for(client, db, sender, creator, "log_out_everywhere")
    clock.advance(timedelta(seconds=1))
    second = code_for(client, db, sender, creator, "log_out_everywhere")

    assert_problem(
        client.post(LOGOUT_ALL_URL, headers=with_header(creator, first)),
        400,
        "step_up_code_invalid",
    )
    assert (
        client.post(LOGOUT_ALL_URL, headers=with_header(creator, second)).status_code
        == 200
    )


def test_five_wrong_tries_use_up_a_code(client, db, sender, creator):
    code = code_for(client, db, sender, creator, "log_out_everywhere")
    for _ in range(5):
        client.post(LOGOUT_ALL_URL, headers=with_header(creator, wrong(code)))

    assert_problem(
        client.post(LOGOUT_ALL_URL, headers=with_header(creator, code)),
        400,
        "step_up_code_invalid",
    )


def test_one_persons_code_is_no_use_to_another(client, db, sender, creator, clock):
    someone = creator_user(db, clock)
    code = code_for(client, db, sender, creator, "download_export")
    code_for(client, db, sender, someone, "download_export")

    assert_problem(
        client.post(EXPORT_URL, headers=with_header(someone, code)),
        400,
        "step_up_code_invalid",
    )


@pytest.mark.parametrize("code", ["12345", "1234567", "12345a", " 12345"])
def test_a_code_that_is_not_six_digits_is_refused(client, creator, code):
    response = client.post(EXPORT_URL, headers=with_header(creator, code))

    assert response.status_code == 422


# --- the export and logging out everywhere ------------------------------------------------


def test_downloading_the_export_tells_the_owner(client, db, creator):
    assert download_export(client, creator.headers).status_code == 200

    assert len(told(db, creator, "data_exported")) == 1


def test_a_refused_export_tells_nobody_anything(client, db, creator):
    client.post(EXPORT_URL, headers=creator.headers)

    assert told(db, creator, "data_exported") == []


def test_the_export_lists_the_codes_but_never_their_hashes(client, db, creator):
    # The file is built after the code that asked for it, before the one
    # that downloads it, so it holds the first (D-111).
    body = download_export(client, creator.headers).json()

    [row] = body["data"]["step_up_codes"]
    assert row["action"] == "download_export"
    assert row["consumed_at"] is not None
    assert set(row) == set(step_up_service.EXPORT_FIELDS)
    assert "hash" not in str(sorted(row))


def test_logging_out_everywhere_needs_a_code(client, db, creator):
    db.add(build_auth_session(db, account_id=creator.account_id))
    db.flush()

    assert_problem(
        client.post(LOGOUT_ALL_URL, headers=creator.headers), 401, "step_up_required"
    )

    sessions = db.scalars(
        select(AuthSession).where(AuthSession.account_id == creator.account_id)
    ).all()
    assert [s.revoked_at for s in sessions] == [None]


def test_logging_out_everywhere_tells_the_owner(client, db, sender, creator):
    for _ in range(2):
        db.add(build_auth_session(db, account_id=creator.account_id))
    db.flush()
    code = code_for(client, db, sender, creator, "log_out_everywhere")

    response = client.post(LOGOUT_ALL_URL, headers=with_header(creator, code))

    assert response.json() == {"sessions_ended": 2}
    [notification] = told(db, creator, "logged_out_everywhere")
    assert notification.details == {"sessions_ended": 2}


# --- admins: the authenticator ------------------------------------------------------------


@pytest.fixture
def admin(db, clock) -> tuple[User, bytes]:
    account = create_account(db, "admin")
    secret = second_factor.new_secret()
    db.add(
        TotpFactor(
            account_id=account.id,
            secret_ciphertext=second_factor_secrets.seal(secret, account.id),
            enrolled_at=clock.now,
            created_at=clock.now,
            updated_at=clock.now,
        )
    )
    db.flush()
    return User(account.id, "admin", clock), secret


def shown(secret: bytes, clock: Clock) -> str:
    return second_factor.code_at_step(secret, second_factor.step_at(clock.now))


def factor_of(db, user: User) -> TotpFactor:
    return db.scalars(
        select(TotpFactor)
        .where(TotpFactor.account_id == user.account_id)
        .execution_options(populate_existing=True)
    ).one()


def test_an_admin_is_sent_nothing(client, db, sender, admin):
    user, _ = admin

    response = ask(client, user, "download_export")

    assert response.status_code == 202
    assert response.json() == {
        "action": "download_export",
        "method": "authenticator",
        "expires_in_seconds": None,
    }
    assert sender.sent == []
    assert (
        db.scalars(
            select(StepUpChallenge).where(StepUpChallenge.account_id == user.account_id)
        ).all()
        == []
    )


def test_an_admin_proves_it_with_the_authenticator(client, db, clock, admin):
    user, secret = admin

    response = client.post(EXPORT_URL, headers=with_header(user, shown(secret, clock)))

    assert response.status_code == 202, response.text


def test_an_admin_s_wrong_code_counts_towards_the_lock(client, db, clock, admin):
    user, secret = admin

    response = client.post(
        EXPORT_URL, headers=with_header(user, wrong(shown(secret, clock)))
    )

    assert_problem(response, 400, "step_up_code_invalid")
    assert factor_of(db, user).consecutive_failures == 1


def test_an_admin_s_code_works_once(client, db, clock, admin):
    user, secret = admin
    code = shown(secret, clock)
    assert client.post(LOGOUT_ALL_URL, headers=with_header(user, code)).status_code == 200

    assert_problem(
        client.post(LOGOUT_ALL_URL, headers=with_header(user, code)),
        400,
        "step_up_code_invalid",
    )


def test_a_locked_authenticator_refuses_even_the_right_code(client, db, clock, admin):
    user, secret = admin
    for _ in range(MAX_CONSECUTIVE_FAILURES):
        client.post(
            LOGOUT_ALL_URL, headers=with_header(user, wrong(shown(secret, clock)))
        )
    assert factor_of(db, user).locked_at is not None

    assert_problem(
        client.post(LOGOUT_ALL_URL, headers=with_header(user, shown(secret, clock))),
        400,
        "step_up_code_invalid",
    )


def test_an_admin_without_an_authenticator_cannot_step_up(client, db, clock):
    user = User(create_account(db, "admin").id, "admin", clock)

    assert_problem(
        client.post(EXPORT_URL, headers=with_header(user, "123456")),
        400,
        "step_up_code_invalid",
    )
