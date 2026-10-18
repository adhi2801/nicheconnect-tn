"""Passkeys (item 79, D-113), through the API.

Adding the first passkey and every later one; logging in with one; a
passkey alone proving every risky change once there is one; removing one;
passkey-only sign-in; the 7-day reset and what cancels it; and every way an
answer can be wrong. Answers come from a software authenticator with a real
key (tests/passkeys.py), so every check runs for real.
"""

import uuid
from collections.abc import Iterator
from contextlib import nullcontext
from datetime import timedelta

import pytest
from fido2.utils import websafe_encode
from sqlalchemy import select

from app.core.config import settings
from app.core.rate_limit import limiter
from app.main import app
from app.modules.auth import step_up_service
from app.modules.auth.models.account import Account
from app.modules.auth.models.auth_session import AuthSession
from app.modules.auth.models.passkey import (
    MAX_PASSKEYS,
    PASSKEY_CHALLENGE_TTL,
    PASSKEY_RESET_WAIT,
    Passkey,
)
from app.modules.auth.models.step_up_challenge import StepUpChallenge
from app.modules.auth.sender import FakeOtpSender, get_otp_sender
from app.modules.auth.tokens import decode_access_token, hash_otp_code
from app.modules.me import passkey_service
from app.modules.notifications.models import Notification
from tests.deal_flow import User, creator_user
from tests.factories import build_auth_session, create_account, unique_test_phone
from tests.passkeys import ORIGIN, RP_ID, SoftAuthenticator
from tests.step_up import STEP_UP_URL, ask_for_code, build_exports

PASSKEYS = "/api/v1/me/passkeys"
LOGIN_OPTIONS = "/api/v1/auth/passkey/options"
LOGIN = "/api/v1/auth/passkey/login"
RESET = "/api/v1/auth/passkey-reset"
OTP_REQUEST = "/api/v1/auth/otp/request"
OTP_VERIFY = "/api/v1/auth/otp/verify"
REFRESH = "/api/v1/auth/refresh"
LOGOUT_ALL = "/api/v1/auth/logout-all"
GRANT = "/api/v1/me/step-up/passkey"


@pytest.fixture(autouse=True)
def passkeys_on(monkeypatch):
    monkeypatch.setattr(settings, "passkey_rp_id", RP_ID)
    monkeypatch.setattr(settings, "passkey_origins", ORIGIN)


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


def told(db, account_id, kind: str) -> list[Notification]:
    return list(
        db.scalars(
            select(Notification).where(
                Notification.account_id == account_id,
                Notification.notification_type == kind,
            )
        ).all()
    )


def phone_of(db, user: User) -> str:
    return db.scalars(select(Account.phone).where(Account.id == user.account_id)).one()


def sign_up_options(client, user: User) -> dict:
    response = client.post(f"{PASSKEYS}/options", headers=user.headers)
    assert response.status_code == 200, response.text
    return response.json()


def add_first(client, user: User, key: SoftAuthenticator, name: str = "My phone"):
    """The first passkey: a phone code for `add_passkey`, then the phone's answer."""
    options = sign_up_options(client, user)
    code = ask_for_code(client, user.headers, "add_passkey")
    return client.post(
        PASSKEYS,
        json={"credential": key.create(options), "name": name},
        headers={**user.headers, "Step-Up-Code": code},
    )


def approve(client, user: User, key: SoftAuthenticator, change: dict) -> str:
    """A passkey's grant for exactly `change`, as an app gets one."""
    asked = client.post(STEP_UP_URL, json=change, headers=user.headers)
    assert asked.status_code == 202, asked.text
    assert asked.json()["method"] == "passkey"
    answer = key.get(asked.json()["passkey_options"])
    granted = client.post(
        GRANT, json={"change": change, "credential": answer}, headers=user.headers
    )
    assert granted.status_code == 200, granted.text
    return granted.json()["code"]


def with_a_passkey(client, user: User) -> SoftAuthenticator:
    key = SoftAuthenticator()
    response = add_first(client, user, key)
    assert response.status_code == 201, response.text
    limiter.reset()
    return key


def log_in_with(client, key: SoftAuthenticator, **answer: object):
    options = client.post(LOGIN_OPTIONS)
    assert options.status_code == 200, options.text
    return client.post(LOGIN, json={"credential": key.get(options.json(), **answer)})


# --- off until the domain exists -------------------------------------------------


def test_passkeys_stay_off_until_the_domain_is_set(client, creator, monkeypatch):
    monkeypatch.setattr(settings, "passkey_rp_id", None)

    assert_problem(
        client.post(f"{PASSKEYS}/options", headers=creator.headers),
        503,
        "passkeys_unavailable",
    )
    assert_problem(client.post(LOGIN_OPTIONS), 503, "passkeys_unavailable")


# --- adding ------------------------------------------------------------------------


def test_the_first_passkey_is_added_with_a_phone_code(client, db, creator):
    key = SoftAuthenticator()

    response = add_first(client, creator, key)

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["name"] == "My phone"
    assert (body["backup_eligible"], body["backup_state"]) == (True, True)
    assert response.headers["location"] == PASSKEYS
    row = db.scalars(
        select(Passkey).where(Passkey.account_id == creator.account_id)
    ).one()
    assert row.credential_id == key.credential_id
    [notice] = told(db, creator.account_id, "passkey_added")
    assert notice.details == {"passkey_id": body["id"], "name": "My phone"}
    listed = client.get(PASSKEYS, headers=creator.headers).json()
    assert [item["id"] for item in listed["items"]] == [body["id"]]
    assert (listed["passkey_only"], listed["reset"]) == (False, None)


def test_the_sign_up_options_ask_for_a_key_unlocked_by_the_phone(client, creator):
    options = sign_up_options(client, creator)["publicKey"]

    assert options["rp"]["id"] == RP_ID
    assert options["authenticatorSelection"]["residentKey"] == "required"
    assert options["authenticatorSelection"]["userVerification"] == "required"


def test_adding_needs_a_code(client, creator):
    options = sign_up_options(client, creator)

    response = client.post(
        PASSKEYS,
        json={"credential": SoftAuthenticator().create(options), "name": "x"},
        headers=creator.headers,
    )

    assert_problem(response, 401, "step_up_required")


def test_a_first_passkey_from_a_new_login_waits_a_week(client, db, clock, creator):
    """A SIM swapper's login is new, but the owner's earlier ones exist."""
    db.add(
        build_auth_session(
            db,
            account_id=creator.account_id,
            created_at=clock.now - timedelta(days=60),
            updated_at=clock.now - timedelta(days=60),
        )
    )
    db.commit()
    creator.logged_in_at = clock.now
    options = sign_up_options(client, creator)
    code = ask_for_code(client, creator.headers, "add_passkey")

    response = client.post(
        PASSKEYS,
        json={"credential": SoftAuthenticator().create(options), "name": "x"},
        headers={**creator.headers, "Step-Up-Code": code},
    )

    assert_problem(response, 403, "login_too_recent")


def test_an_accounts_very_first_login_may_add_its_first_passkey(client, db, sender):
    phone = unique_test_phone()
    client.post(OTP_REQUEST, json={"phone": phone})
    tokens = client.post(
        OTP_VERIFY,
        json={"phone": phone, "code": sender.last_code_for(phone), "role": "creator"},
    ).json()
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    options = client.post(f"{PASSKEYS}/options", headers=headers).json()
    code = ask_for_code(client, headers, "add_passkey")

    response = client.post(
        PASSKEYS,
        json={"credential": SoftAuthenticator().create(options), "name": "x"},
        headers={**headers, "Step-Up-Code": code},
    )

    assert response.status_code == 201, response.text


def test_a_later_passkey_needs_a_passkey_never_a_phone_code(client, db, sender, creator):
    first = with_a_passkey(client, creator)
    sender.clear()

    asked = client.post(
        STEP_UP_URL, json={"action": "add_passkey"}, headers=creator.headers
    )
    code = approve(client, creator, first, {"action": "add_passkey"})
    options = sign_up_options(client, creator)
    second = SoftAuthenticator()
    response = client.post(
        PASSKEYS,
        json={"credential": second.create(options), "name": "Laptop"},
        headers={**creator.headers, "Step-Up-Code": code},
    )

    assert asked.json()["method"] == "passkey"
    assert sender.sent == []
    assert response.status_code == 201, response.text
    assert len(client.get(PASSKEYS, headers=creator.headers).json()["items"]) == 2


@pytest.mark.parametrize(
    "spoil",
    [
        {"origin": "https://nicheconnect.test.evil.example"},
        {"rp_id": "evil.example"},
        {"verified": False},
    ],
    ids=["another origin", "another domain", "not unlocked by the phone"],
)
def test_a_wrong_sign_up_answer_is_refused(client, creator, spoil):
    options = sign_up_options(client, creator)
    code = ask_for_code(client, creator.headers, "add_passkey")

    response = client.post(
        PASSKEYS,
        json={"credential": SoftAuthenticator().create(options, **spoil), "name": "x"},
        headers={**creator.headers, "Step-Up-Code": code},
    )

    assert_problem(response, 400, "passkey_invalid")


def test_a_sign_up_challenge_works_once_and_for_five_minutes(client, clock, creator):
    options = sign_up_options(client, creator)
    key = SoftAuthenticator()
    clock.advance(PASSKEY_CHALLENGE_TTL)
    code = ask_for_code(client, creator.headers, "add_passkey")

    late = client.post(
        PASSKEYS,
        json={"credential": key.create(options), "name": "x"},
        headers={**creator.headers, "Step-Up-Code": code},
    )

    assert_problem(late, 400, "passkey_invalid")


def test_someone_elses_sign_up_challenge_is_no_use(client, db, clock, creator):
    someone = creator_user(db, clock)
    db.commit()
    theirs = sign_up_options(client, someone)
    code = ask_for_code(client, creator.headers, "add_passkey")

    response = client.post(
        PASSKEYS,
        json={"credential": SoftAuthenticator().create(theirs), "name": "x"},
        headers={**creator.headers, "Step-Up-Code": code},
    )

    assert_problem(response, 400, "passkey_invalid")


def test_a_challenge_made_for_a_change_cannot_sign_up_a_key(client, creator):
    key = with_a_passkey(client, creator)
    code = approve(client, creator, key, {"action": "add_passkey"})
    asked = client.post(
        STEP_UP_URL, json={"action": "log_out_everywhere"}, headers=creator.headers
    ).json()
    change_challenge = asked["passkey_options"]["publicKey"]["challenge"]
    options = {
        "publicKey": {
            "challenge": change_challenge,
            "user": {"id": websafe_encode(uuid.UUID(str(creator.account_id)).bytes)},
        }
    }

    response = client.post(
        PASSKEYS,
        json={"credential": SoftAuthenticator().create(options), "name": "x"},
        headers={**creator.headers, "Step-Up-Code": code},
    )

    assert_problem(response, 400, "passkey_invalid")


def test_passkey_approvals_use_none_of_the_phones_messages(
    client, db, sender, clock, creator
):
    key = with_a_passkey(client, creator)
    clock.advance(timedelta(minutes=11))
    for _ in range(3):
        approve(client, creator, key, {"action": "log_out_everywhere"})
        limiter.reset()

    response = client.post(OTP_REQUEST, json={"phone": phone_of(db, creator)})

    assert response.status_code == 202, response.text


def test_an_account_holds_ten_passkeys_at_most(client, db, clock, creator):
    key = with_a_passkey(client, creator)
    for n in range(MAX_PASSKEYS - 1):
        db.add(
            Passkey(
                account_id=creator.account_id,
                credential_id=uuid.uuid4().bytes,
                public_key=b"\xa0",
                sign_count=0,
                aaguid=uuid.UUID(int=0),
                backup_eligible=False,
                backup_state=False,
                name=f"spare {n}",
                created_at=clock.now,
                updated_at=clock.now,
            )
        )
    db.commit()
    code = approve(client, creator, key, {"action": "add_passkey"})
    options = sign_up_options(client, creator)

    response = client.post(
        PASSKEYS,
        json={"credential": SoftAuthenticator().create(options), "name": "eleventh"},
        headers={**creator.headers, "Step-Up-Code": code},
    )

    assert_problem(response, 409, "too_many_passkeys")


def test_admins_add_no_passkeys_yet(client, db, clock):
    admin = User(create_account(db, "admin").id, "admin", clock)
    db.commit()

    assert_problem(
        client.post(f"{PASSKEYS}/options", headers=admin.headers), 403, "role_not_allowed"
    )


# --- logging in --------------------------------------------------------------------


def test_a_passkey_logs_in_and_its_tokens_say_so_through_every_refresh(
    client, db, clock, creator
):
    key = with_a_passkey(client, creator)

    response = log_in_with(client, key)
    clock.advance(timedelta(minutes=20))
    refreshed = client.post(
        REFRESH, json={"refresh_token": response.json()["refresh_token"]}
    )

    assert response.status_code == 200, response.text
    assert response.json()["account"] == {
        "id": str(creator.account_id),
        "role": "creator",
        "is_new": False,
    }
    first = decode_access_token(
        response.json()["access_token"], clock.now - timedelta(minutes=20)
    )
    later = decode_access_token(refreshed.json()["access_token"], clock.now)
    assert first.methods == later.methods == ("pop", "user")
    session = db.scalars(
        select(AuthSession).where(AuthSession.account_id == creator.account_id)
    ).first()
    assert session is not None and session.passkey_at is not None


@pytest.mark.parametrize(
    "spoil",
    [
        {"origin": "https://elsewhere.example"},
        {"rp_id": "evil.example"},
        {"verified": False},
    ],
    ids=["another origin", "another domain", "not unlocked by the phone"],
)
def test_a_wrong_login_answer_is_refused(client, creator, spoil):
    key = with_a_passkey(client, creator)

    assert_problem(log_in_with(client, key, **spoil), 400, "passkey_invalid")


def test_a_key_we_never_saw_is_refused(client, creator):
    assert_problem(log_in_with(client, SoftAuthenticator()), 400, "passkey_invalid")


def test_a_login_answer_works_once(client, creator):
    key = with_a_passkey(client, creator)
    options = client.post(LOGIN_OPTIONS).json()
    answer = key.get(options)

    first = client.post(LOGIN, json={"credential": answer})
    again = client.post(LOGIN, json={"credential": answer})

    assert first.status_code == 200, first.text
    assert_problem(again, 400, "passkey_invalid")


def test_a_counter_gone_backwards_refuses_the_key(client, creator):
    key = SoftAuthenticator(synced=False, counter_step=1)
    assert add_first(client, creator, key).status_code == 201
    assert log_in_with(client, key).status_code == 200

    replayed = log_in_with(client, key, counter=1)

    assert_problem(replayed, 400, "passkey_invalid")


def test_a_suspended_account_cannot_log_in_with_its_passkey(client, db, clock, creator):
    key = with_a_passkey(client, creator)
    account = db.get_one(Account, creator.account_id)
    account.suspended_at = clock.now
    account.suspension_reason = "spam"
    db.commit()

    assert_problem(log_in_with(client, key), 403, "account_suspended")


# --- a passkey alone proves a change -----------------------------------------------


def test_with_a_passkey_a_change_is_proven_by_it_and_no_message_is_sent(
    client, db, sender, creator
):
    key = with_a_passkey(client, creator)
    sender.clear()

    code = approve(client, creator, key, {"action": "log_out_everywhere"})
    response = client.post(LOGOUT_ALL, headers={**creator.headers, "Step-Up-Code": code})

    assert response.status_code == 200, response.text
    assert sender.sent == []


def test_with_a_passkey_a_phone_code_proves_nothing(client, db, clock, creator):
    with_a_passkey(client, creator)
    db.add(
        StepUpChallenge(
            account_id=creator.account_id,
            action="log_out_everywhere",
            value_hash=step_up_service.value_hash("log_out_everywhere", ""),
            code_hash=hash_otp_code("123456"),
            method="phone_code",
            expires_at=clock.now + timedelta(minutes=5),
            created_at=clock.now,
            updated_at=clock.now,
        )
    )
    db.commit()

    response = client.post(
        LOGOUT_ALL, headers={**creator.headers, "Step-Up-Code": "123456"}
    )

    assert_problem(response, 400, "step_up_code_invalid")


def test_a_passkey_answer_for_one_change_cannot_approve_another(client, creator):
    key = with_a_passkey(client, creator)
    asked = client.post(
        STEP_UP_URL, json={"action": "log_out_everywhere"}, headers=creator.headers
    ).json()

    response = client.post(
        GRANT,
        json={
            "change": {"action": "add_passkey"},
            "credential": key.get(asked["passkey_options"]),
        },
        headers=creator.headers,
    )

    assert_problem(response, 400, "passkey_invalid")


def test_a_grant_for_one_change_cannot_make_another(client, creator):
    key = with_a_passkey(client, creator)
    code = approve(client, creator, key, {"action": "add_passkey"})

    response = client.post(LOGOUT_ALL, headers={**creator.headers, "Step-Up-Code": code})

    assert_problem(response, 400, "step_up_code_invalid")


def test_someone_elses_passkey_cannot_approve_your_change(client, db, clock, creator):
    with_a_passkey(client, creator)
    someone = creator_user(db, clock)
    db.commit()
    theirs = with_a_passkey(client, someone)
    asked = client.post(
        STEP_UP_URL, json={"action": "log_out_everywhere"}, headers=creator.headers
    ).json()

    response = client.post(
        GRANT,
        json={
            "change": {"action": "log_out_everywhere"},
            "credential": theirs.get(asked["passkey_options"]),
        },
        headers=creator.headers,
    )

    assert_problem(response, 400, "passkey_invalid")


def test_with_a_passkey_a_new_login_need_not_wait_a_week(client, clock, creator):
    with_a_passkey(client, creator)
    creator.logged_in_at = clock.now

    asked = client.post(
        STEP_UP_URL,
        json={"action": "change_phone", "new_phone": unique_test_phone()},
        headers=creator.headers,
    )

    assert asked.status_code == 202, asked.text
    assert asked.json()["method"] == "passkey"


def test_with_a_passkey_the_lost_number_path_needs_it_too(client, sender, creator):
    with_a_passkey(client, creator)
    new_phone = unique_test_phone()
    client.post(OTP_REQUEST, json={"phone": new_phone})

    response = client.post(
        "/api/v1/me/phone-change/without-current-number",
        json={"new_phone": new_phone, "new_phone_code": sender.last_code_for(new_phone)},
        headers=creator.headers,
    )

    assert_problem(response, 401, "step_up_required")


# --- removing, renaming ------------------------------------------------------------


def test_a_passkey_is_removed_with_its_own_approval(client, db, creator):
    key = with_a_passkey(client, creator)
    passkey_id = client.get(PASSKEYS, headers=creator.headers).json()["items"][0]["id"]
    code = approve(
        client, creator, key, {"action": "remove_passkey", "passkey_id": passkey_id}
    )

    response = client.delete(
        f"{PASSKEYS}/{passkey_id}", headers={**creator.headers, "Step-Up-Code": code}
    )

    assert response.status_code == 204, response.text
    assert client.get(PASSKEYS, headers=creator.headers).json()["items"] == []
    [notice] = told(db, creator.account_id, "passkey_removed")
    assert notice.details == {"count": 1, "reason": "removed"}


def test_removing_needs_the_approval_for_that_passkey(client, db, clock, creator):
    key = with_a_passkey(client, creator)
    add_code = approve(client, creator, key, {"action": "add_passkey"})
    options = sign_up_options(client, creator)
    client.post(
        PASSKEYS,
        json={"credential": SoftAuthenticator().create(options), "name": "Laptop"},
        headers={**creator.headers, "Step-Up-Code": add_code},
    )
    limiter.reset()
    first, second = [
        item["id"]
        for item in client.get(PASSKEYS, headers=creator.headers).json()["items"]
    ]
    code = approve(
        client, creator, key, {"action": "remove_passkey", "passkey_id": first}
    )

    response = client.delete(
        f"{PASSKEYS}/{second}", headers={**creator.headers, "Step-Up-Code": code}
    )

    assert_problem(response, 400, "step_up_code_invalid")


def test_approving_removal_of_a_passkey_not_yours_is_refused_before_asking(
    client, creator
):
    key = with_a_passkey(client, creator)

    asked = client.post(
        STEP_UP_URL,
        json={"action": "remove_passkey", "passkey_id": str(uuid.uuid4())},
        headers=creator.headers,
    )

    assert_problem(asked, 404, "passkey_not_found")
    assert key.counter == 0


def test_a_passkey_is_renamed_with_no_code(client, creator):
    with_a_passkey(client, creator)
    passkey_id = client.get(PASSKEYS, headers=creator.headers).json()["items"][0]["id"]

    response = client.patch(
        f"{PASSKEYS}/{passkey_id}",
        json={"name": "  Old phone  "},
        headers=creator.headers,
    )

    assert response.json()["name"] == "Old phone"


def test_nobody_else_can_rename_or_remove_yours(client, db, clock, creator):
    with_a_passkey(client, creator)
    passkey_id = client.get(PASSKEYS, headers=creator.headers).json()["items"][0]["id"]
    someone = creator_user(db, clock)
    db.commit()

    renamed = client.patch(
        f"{PASSKEYS}/{passkey_id}", json={"name": "mine now"}, headers=someone.headers
    )
    removed = client.delete(
        f"{PASSKEYS}/{passkey_id}", headers={**someone.headers, "Step-Up-Code": "123456"}
    )

    assert_problem(renamed, 404, "passkey_not_found")
    assert_problem(removed, 404, "passkey_not_found")


# --- passkey-only sign-in ----------------------------------------------------------


def turn_passkey_only(client, user: User, key: SoftAuthenticator, enabled: bool):
    code = approve(client, user, key, {"action": "passkey_only", "enabled": enabled})
    return client.put(
        f"{PASSKEYS}/only",
        json={"enabled": enabled},
        headers={**user.headers, "Step-Up-Code": code},
    )


def test_with_passkey_only_on_a_phone_code_no_longer_logs_in(client, db, sender, creator):
    key = with_a_passkey(client, creator)

    response = turn_passkey_only(client, creator, key, True)
    phone = phone_of(db, creator)
    client.post(OTP_REQUEST, json={"phone": phone})
    code = sender.last_code_for(phone)
    by_code = client.post(
        OTP_VERIFY, json={"phone": phone, "code": code, "role": "creator"}
    )
    reset = client.post(RESET, json={"phone": phone, "code": code})

    assert response.json()["passkey_only"] is True
    assert told(db, creator.account_id, "passkey_only_changed")[0].details == {
        "passkey_only": True
    }
    assert_problem(by_code, 403, "passkey_only")
    # The code stayed usable, for the one thing it can still do.
    assert reset.status_code == 202, reset.text
    assert log_in_with(client, key).status_code == 200


def test_passkey_only_needs_a_passkey_first(client, creator):
    code = ask_for_code(client, creator.headers, "passkey_only", enabled="true")

    response = client.put(
        f"{PASSKEYS}/only",
        json={"enabled": True},
        headers={**creator.headers, "Step-Up-Code": code},
    )

    assert_problem(response, 409, "passkey_needed_first")


def test_an_approval_to_turn_it_on_cannot_turn_it_off(client, creator):
    key = with_a_passkey(client, creator)
    code = approve(client, creator, key, {"action": "passkey_only", "enabled": True})

    response = client.put(
        f"{PASSKEYS}/only",
        json={"enabled": False},
        headers={**creator.headers, "Step-Up-Code": code},
    )

    assert_problem(response, 400, "step_up_code_invalid")


def test_removing_the_last_passkey_turns_passkey_only_off(client, db, creator):
    key = with_a_passkey(client, creator)
    turn_passkey_only(client, creator, key, True)
    limiter.reset()
    passkey_id = client.get(PASSKEYS, headers=creator.headers).json()["items"][0]["id"]
    code = approve(
        client, creator, key, {"action": "remove_passkey", "passkey_id": passkey_id}
    )

    client.delete(
        f"{PASSKEYS}/{passkey_id}", headers={**creator.headers, "Step-Up-Code": code}
    )

    assert client.get(PASSKEYS, headers=creator.headers).json()["passkey_only"] is False


# --- the reset ---------------------------------------------------------------------


def start_reset(client, db, sender, user: User):
    phone = phone_of(db, user)
    client.post(OTP_REQUEST, json={"phone": phone})
    return client.post(RESET, json={"phone": phone, "code": sender.last_code_for(phone)})


def run_job(db, clock) -> passkey_service.ResetRun:
    return passkey_service.run_resets(lambda: nullcontext(db), clock.now)


def test_a_reset_waits_seven_days_then_removes_every_passkey(
    client, db, sender, clock, creator
):
    key = with_a_passkey(client, creator)
    turn_passkey_only(client, creator, key, True)

    response = start_reset(client, db, sender, creator)
    clock.advance(PASSKEY_RESET_WAIT - timedelta(seconds=1))
    early = run_job(db, clock)
    clock.advance(timedelta(seconds=1))
    due = run_job(db, clock)

    assert response.status_code == 202, response.text
    assert response.json()["takes_effect_at"].startswith((clock.now).isoformat()[:19])
    assert (early.reset, due.reset) == (0, 1)
    assert (
        db.scalars(select(Passkey).where(Passkey.account_id == creator.account_id)).all()
        == []
    )
    assert db.get_one(Account, creator.account_id).passkey_only is False
    assert len(told(db, creator.account_id, "passkey_reset_requested")) == 1
    [removed] = told(db, creator.account_id, "passkey_removed")
    assert removed.details == {"count": 1, "reason": "reset"}


def test_any_passkey_sign_in_cancels_a_reset(client, db, sender, clock, creator):
    key = with_a_passkey(client, creator)
    start_reset(client, db, sender, creator)
    clock.advance(timedelta(days=1))

    assert log_in_with(client, key).status_code == 200
    shown = client.get(PASSKEYS, headers=creator.headers).json()
    run = run_job(db, clock)
    clock.advance(PASSKEY_RESET_WAIT)
    later = run_job(db, clock)

    assert shown["reset"] is None
    assert (run.cancelled, later.reset) == (1, 0)
    assert len(client.get(PASSKEYS, headers=creator.headers).json()["items"]) == 1
    assert len(told(db, creator.account_id, "passkey_reset_cancelled")) == 1


def test_asking_again_never_moves_the_reset(client, db, sender, clock, creator):
    with_a_passkey(client, creator)
    first = start_reset(client, db, sender, creator).json()
    clock.advance(timedelta(days=2))
    limiter.reset()

    again = start_reset(client, db, sender, creator).json()

    assert again["takes_effect_at"] == first["takes_effect_at"]
    assert len(told(db, creator.account_id, "passkey_reset_requested")) == 1


def test_a_number_without_a_passkey_has_nothing_to_reset(client, db, sender, creator):
    assert_problem(start_reset(client, db, sender, creator), 409, "no_passkey_to_reset")


def test_a_reset_needs_the_numbers_right_code(client, db, sender, creator):
    with_a_passkey(client, creator)
    phone = phone_of(db, creator)
    client.post(OTP_REQUEST, json={"phone": phone})
    code = sender.last_code_for(phone)

    response = client.post(
        RESET, json={"phone": phone, "code": f"{(int(code) + 1) % 10**6:06d}"}
    )

    assert_problem(response, 400, "otp_invalid")


def test_old_challenges_are_tidied_away(client, db, clock, creator):
    with_a_passkey(client, creator)
    client.post(LOGIN_OPTIONS)
    clock.advance(timedelta(days=2))

    run = run_job(db, clock)

    assert run.challenges_removed >= 1


# --- the export --------------------------------------------------------------------


def test_the_export_holds_the_passkeys_but_never_their_keys(client, db, creator):
    key = with_a_passkey(client, creator)
    log_in_with(client, key)
    limiter.reset()
    # The export's own download is proven by the passkey too.
    asked = client.post("/api/v1/me/exports", headers=creator.headers)
    build_exports()
    export_id = asked.json()["id"]
    code = approve(
        client, creator, key, {"action": "download_export", "export_id": export_id}
    )
    data = client.post(
        f"/api/v1/me/exports/{export_id}/download",
        headers={**creator.headers, "Step-Up-Code": code},
    ).json()["data"]

    [row] = data["passkeys"]
    assert set(row) == set(passkey_service.PASSKEY_EXPORT_FIELDS)
    assert "public_key" not in row and "credential_id" not in row
    assert any(s["passkey_at"] is not None for s in data["login_sessions"])
