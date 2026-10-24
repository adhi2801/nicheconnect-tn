"""Where you are logged in, and ending one session (item 81, D-114), through the API.

Each session is a real login (`service.issue_session`, as every login path
makes one), so its access token carries its `sid` and every request checks
it is still live.
"""

import uuid
from collections.abc import Iterator
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.main import app
from app.modules.auth import service as login
from app.modules.auth.models.account import Account
from app.modules.auth.models.auth_session import AuthSession
from app.modules.auth.models.step_up_challenge import StepUpChallenge
from app.modules.auth.sender import FakeOtpSender, get_otp_sender
from app.modules.auth.service import ClientDevice, LoginResult
from app.modules.notifications.models import Notification
from tests.factories import create_account, fake_phone
from tests.query_counts import queries_for

SESSIONS_URL = "/api/v1/me/sessions"
STEP_UP_URL = "/api/v1/me/step-up"
ME_URL = "/api/v1/auth/me"
REFRESH_URL = "/api/v1/auth/refresh"
PIXEL = ClientDevice(platform="android", label="Pixel 8")
CHROME = ClientDevice(platform="web", label="Chrome on Windows")


@pytest.fixture
def sender(client) -> Iterator[FakeOtpSender]:
    fake = FakeOtpSender()
    app.dependency_overrides[get_otp_sender] = lambda: fake
    yield fake
    app.dependency_overrides.pop(get_otp_sender, None)


@pytest.fixture
def account(db) -> Account:
    return create_account(db, "creator")


def sign_in(db, account: Account, clock, device: ClientDevice | None = None, **kw):
    """A real login of `account` at the clock's time: a new session family."""
    result = login.issue_session(
        db, account, uuid.uuid4(), clock.now, device=device, **kw
    )
    db.flush()
    return result


def auth(result: LoginResult) -> dict[str, str]:
    return {"Authorization": f"Bearer {result.access_token}"}


def sid(db, result: LoginResult) -> str:
    """The session id a login made: its family's."""
    from app.modules.auth.tokens import hash_refresh_token

    row = db.scalars(
        select(AuthSession).where(
            AuthSession.token_hash == hash_refresh_token(result.refresh_token)
        )
    ).one()
    return str(row.family_id)


def assert_problem(response, status: int, code: str) -> None:
    assert response.status_code == status, response.text
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["code"] == code


def code_to_end(client, db, sender, headers, account: Account, session_id: str) -> str:
    response = client.post(
        STEP_UP_URL,
        json={"action": "end_session", "session_id": session_id},
        headers=headers,
    )
    assert response.status_code == 202, response.text
    code = sender.last_code_for(account.phone)
    assert code is not None
    return code


def told(db, account: Account) -> list[Notification]:
    return list(
        db.scalars(
            select(Notification).where(
                Notification.account_id == account.id,
                Notification.notification_type == "session_ended",
            )
        ).all()
    )


# --- listing ------------------------------------------------------------------------------


def test_each_session_is_listed_with_its_device_and_how_it_signed_in(
    client, db, clock, account
):
    phone = sign_in(db, account, clock, PIXEL)
    clock.advance(timedelta(hours=2))
    laptop = sign_in(db, account, clock, CHROME, passkey_at=clock.now)

    response = client.get(SESSIONS_URL, headers=auth(laptop))

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["next_cursor"] is None
    assert [
        (s["id"], s["platform"], s["label"], s["signed_in_with"], s["is_current"])
        for s in body["items"]
    ] == [
        (sid(db, laptop), "web", "Chrome on Windows", "passkey", True),
        (sid(db, phone), "android", "Pixel 8", "phone_code", False),
    ]
    first = body["items"][1]
    assert first["signed_in_at"] == first["last_active_at"]
    assert first["expires_at"] > first["signed_in_at"]


def test_a_session_that_named_no_device_is_listed_without_one(client, db, clock, account):
    result = sign_in(db, account, clock)

    [item] = client.get(SESSIONS_URL, headers=auth(result)).json()["items"]

    assert (item["platform"], item["label"]) == (None, None)


def test_a_refresh_keeps_the_sign_in_time_and_device_and_moves_last_active(
    client, db, clock, account
):
    first = sign_in(db, account, clock, PIXEL)
    signed_in = clock.now
    clock.advance(timedelta(minutes=20))

    refreshed = client.post(REFRESH_URL, json={"refresh_token": first.refresh_token})
    assert refreshed.status_code == 200, refreshed.text
    headers = {"Authorization": f"Bearer {refreshed.json()['access_token']}"}

    [item] = client.get(SESSIONS_URL, headers=headers).json()["items"]
    assert item["id"] == sid(db, first)
    assert item["label"] == "Pixel 8"
    assert item["is_current"] is True
    assert item["signed_in_at"].startswith(signed_in.isoformat()[:19])
    assert item["last_active_at"].startswith(clock.now.isoformat()[:19])


def test_ended_expired_and_other_accounts_sessions_are_not_listed(
    client, db, clock, account
):
    mine = sign_in(db, account, clock, PIXEL)
    ended = sign_in(db, account, clock, CHROME)
    login.logout(db, ended.refresh_token, clock.now)
    stale = sign_in(db, account, clock, CHROME)
    db.execute(
        AuthSession.__table__.update()
        .where(AuthSession.token_hash == _hash(stale))
        .values(expires_at=clock.now - timedelta(seconds=1))
    )
    someone_else = create_account(db, "creator")
    sign_in(db, someone_else, clock, PIXEL)
    sign_in(db, someone_else, clock, CHROME)

    items = client.get(SESSIONS_URL, headers=auth(mine)).json()["items"]

    assert [item["id"] for item in items] == [sid(db, mine)]


def _hash(result: LoginResult) -> str:
    from app.modules.auth.tokens import hash_refresh_token

    return hash_refresh_token(result.refresh_token)


def test_pages_have_no_gaps_or_repeats_even_when_sign_ins_share_a_moment(
    client, db, clock, account
):
    made = [sign_in(db, account, clock, PIXEL) for _ in range(5)]
    expected = sorted((sid(db, r) for r in made), reverse=True)

    seen: list[str] = []
    cursor = None
    while True:
        params = {"limit": 2, **({"cursor": cursor} if cursor else {})}
        body = client.get(SESSIONS_URL, headers=auth(made[0]), params=params).json()
        seen += [item["id"] for item in body["items"]]
        cursor = body["next_cursor"]
        if cursor is None:
            break

    assert seen == expected


def test_a_long_list_costs_the_same_queries_as_a_short_one(client, db, clock, account):
    current = sign_in(db, account, clock, PIXEL)
    short = queries_for(client, SESSIONS_URL, auth(current))
    for _ in range(8):
        sign_in(db, account, clock, CHROME)

    assert queries_for(client, SESSIONS_URL, auth(current)) == short


@pytest.mark.parametrize(
    "params", [{"limit": 0}, {"limit": 101}, {"cursor": "not-a-cursor"}]
)
def test_a_bad_page_request_is_refused(client, db, clock, account, params):
    result = sign_in(db, account, clock)

    response = client.get(SESSIONS_URL, headers=auth(result), params=params)

    assert response.status_code == 422, response.text


def test_listing_needs_a_login(client):
    assert_problem(client.get(SESSIONS_URL), 401, "invalid_token")


# --- an ended session's access token stops at once ---------------------------------------


def test_after_logout_the_access_token_is_refused_at_once(client, db, clock, account):
    result = sign_in(db, account, clock, PIXEL)
    assert client.get(ME_URL, headers=auth(result)).status_code == 200

    login.logout(db, result.refresh_token, clock.now)

    assert_problem(client.get(ME_URL, headers=auth(result)), 401, "invalid_token")


def test_a_token_from_before_sessions_were_named_still_works(client, db, clock, account):
    """Tokens signed before D-114 carry no `sid`; they live out their 15 minutes."""
    from app.modules.auth.tokens import create_access_token

    token, _ = create_access_token(account.id, "creator", clock.now)

    response = client.get(ME_URL, headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200, response.text


def test_a_suspended_account_is_still_told_it_is_suspended(client, db, clock, account):
    """The session check comes after the suspension check, so the answer is the same."""
    result = sign_in(db, account, clock)
    account.suspended_at = clock.now
    account.suspension_reason = "fake_profile"
    db.flush()

    assert_problem(client.get(ME_URL, headers=auth(result)), 403, "account_suspended")


# --- ending one session -------------------------------------------------------------------


def test_ending_this_session_needs_no_code_and_logs_it_out(client, db, clock, account):
    result = sign_in(db, account, clock, PIXEL)

    response = client.delete(f"{SESSIONS_URL}/{sid(db, result)}", headers=auth(result))

    assert response.status_code == 204, response.text
    assert_problem(client.get(ME_URL, headers=auth(result)), 401, "invalid_token")
    refused = client.post(REFRESH_URL, json={"refresh_token": result.refresh_token})
    assert refused.status_code == 401
    assert told(db, account) == []


def test_ending_another_session_needs_a_code(client, db, clock, account):
    phone = sign_in(db, account, clock, PIXEL)
    laptop = sign_in(db, account, clock, CHROME)

    response = client.delete(f"{SESSIONS_URL}/{sid(db, phone)}", headers=auth(laptop))

    assert_problem(response, 401, "step_up_required")
    assert client.get(ME_URL, headers=auth(phone)).status_code == 200


def test_another_session_ends_with_its_code_at_once_and_the_owner_is_told(
    client, db, clock, sender, account
):
    stolen = sign_in(db, account, clock, PIXEL)
    owner = sign_in(db, account, clock, CHROME)
    code = code_to_end(client, db, sender, auth(owner), account, sid(db, stolen))

    response = client.delete(
        f"{SESSIONS_URL}/{sid(db, stolen)}",
        headers={**auth(owner), "Step-Up-Code": code},
    )

    assert response.status_code == 204, response.text
    assert_problem(client.get(ME_URL, headers=auth(stolen)), 401, "invalid_token")
    refused = client.post(REFRESH_URL, json={"refresh_token": stolen.refresh_token})
    assert refused.status_code == 401
    assert client.get(ME_URL, headers=auth(owner)).status_code == 200
    [notice] = told(db, account)
    assert notice.details == {
        "session_id": sid(db, stolen),
        "device_platform": "android",
        "device_label": "Pixel 8",
    }
    remaining = client.get(SESSIONS_URL, headers=auth(owner)).json()["items"]
    assert [item["id"] for item in remaining] == [sid(db, owner)]


def test_a_code_for_one_session_cannot_end_another(client, db, clock, sender, account):
    first = sign_in(db, account, clock, PIXEL)
    second = sign_in(db, account, clock, PIXEL)
    owner = sign_in(db, account, clock, CHROME)
    code = code_to_end(client, db, sender, auth(owner), account, sid(db, first))

    response = client.delete(
        f"{SESSIONS_URL}/{sid(db, second)}",
        headers={**auth(owner), "Step-Up-Code": code},
    )

    assert_problem(response, 400, "step_up_code_invalid")
    assert client.get(ME_URL, headers=auth(second)).status_code == 200


def test_a_code_ends_a_session_once(client, db, clock, sender, account):
    other = sign_in(db, account, clock, PIXEL)
    owner = sign_in(db, account, clock, CHROME)
    code = code_to_end(client, db, sender, auth(owner), account, sid(db, other))
    headers = {**auth(owner), "Step-Up-Code": code}
    assert (
        client.delete(f"{SESSIONS_URL}/{sid(db, other)}", headers=headers).status_code
        == 204
    )

    again = client.delete(f"{SESSIONS_URL}/{sid(db, other)}", headers=headers)

    assert_problem(again, 404, "session_not_found")


@pytest.mark.parametrize("whose", ["unknown", "another_account", "ended"])
def test_a_session_that_is_not_a_live_one_of_yours_is_not_found(
    client, db, clock, account, whose
):
    owner = sign_in(db, account, clock, CHROME)
    if whose == "unknown":
        target = str(uuid.uuid4())
    elif whose == "another_account":
        target = sid(db, sign_in(db, create_account(db, "creator"), clock, PIXEL))
    else:
        ended = sign_in(db, account, clock, PIXEL)
        login.logout(db, ended.refresh_token, clock.now)
        target = sid(db, ended)

    response = client.delete(f"{SESSIONS_URL}/{target}", headers=auth(owner))

    assert_problem(response, 404, "session_not_found")


def test_no_code_is_sent_for_a_session_that_is_not_yours(
    client, db, clock, sender, account
):
    owner = sign_in(db, account, clock, CHROME)
    theirs = sign_in(db, create_account(db, "brand"), clock, PIXEL)

    response = client.post(
        STEP_UP_URL,
        json={"action": "end_session", "session_id": sid(db, theirs)},
        headers=auth(owner),
    )

    assert_problem(response, 404, "session_not_found")
    assert sender.sent == []
    assert db.scalars(select(StepUpChallenge)).all() == []


def test_a_wrong_session_id_spends_no_code(client, db, clock, sender, account):
    other = sign_in(db, account, clock, PIXEL)
    owner = sign_in(db, account, clock, CHROME)
    code = code_to_end(client, db, sender, auth(owner), account, sid(db, other))

    missing = client.delete(
        f"{SESSIONS_URL}/{uuid.uuid4()}", headers={**auth(owner), "Step-Up-Code": code}
    )
    kept = client.delete(
        f"{SESSIONS_URL}/{sid(db, other)}", headers={**auth(owner), "Step-Up-Code": code}
    )

    assert_problem(missing, 404, "session_not_found")
    assert kept.status_code == 204, kept.text


def test_ending_a_session_needs_a_login(client):
    assert_problem(client.delete(f"{SESSIONS_URL}/{uuid.uuid4()}"), 401, "invalid_token")


def test_a_malformed_session_id_is_refused(client, db, clock, account):
    result = sign_in(db, account, clock)

    assert (
        client.delete(f"{SESSIONS_URL}/not-a-uuid", headers=auth(result)).status_code
        == 422
    )


# --- naming the device at login -----------------------------------------------------------


def otp_login(client, sender, phone: str, **extra: object):
    assert (
        client.post("/api/v1/auth/otp/request", json={"phone": phone}).status_code == 202
    )
    return client.post(
        "/api/v1/auth/otp/verify",
        json={
            "phone": phone,
            "code": sender.last_code_for(phone),
            "role": "creator",
            **extra,
        },
    )


def test_a_code_login_names_its_device(client, db, sender):
    response = otp_login(
        client, sender, fake_phone(), device={"platform": "ios", "label": "  iPhone 15  "}
    )

    assert response.status_code == 200, response.text
    headers = {"Authorization": f"Bearer {response.json()['access_token']}"}
    [item] = client.get(SESSIONS_URL, headers=headers).json()["items"]
    assert (item["platform"], item["label"], item["is_current"]) == (
        "ios",
        "iPhone 15",
        True,
    )


@pytest.mark.parametrize(
    "device",
    [
        {"platform": "windows", "label": "My PC"},
        {"platform": "android", "label": ""},
        {"platform": "android", "label": "   "},
        {"platform": "android", "label": "x" * 61},
        {"platform": "android", "label": "Pixel" + chr(10) + "8"},
        {"platform": "android", "label": "Pixel" + chr(0x2028) + "8"},
        {"platform": "android"},
        {"label": "Pixel 8"},
        {"platform": "android", "label": "Pixel 8", "model": "GKWS6"},
    ],
)
def test_a_device_that_cannot_be_shown_is_refused(client, sender, device):
    response = otp_login(client, sender, fake_phone(), device=device)

    assert response.status_code == 422, response.text
