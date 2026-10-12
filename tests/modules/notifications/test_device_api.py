"""Phones registered for push notifications (item 9, D-095)."""

import uuid
from collections.abc import Iterator
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.core.rate_limit import limiter
from app.db.session import get_db
from app.main import app
from app.modules.auth.dependencies import get_now
from app.modules.auth.sender import FakeOtpSender, get_otp_sender
from app.modules.auth.tokens import decode_access_token
from app.modules.notifications.device_models import MAX_DEVICES_PER_ACCOUNT, DeviceToken
from tests.deal_flow import Clock
from tests.factories import FIXED_NOW
from tests.modules.auth.test_refresh_api import LOGOUT_URL, log_in

URL = "/api/v1/me/devices"
EXPORT_URL = "/api/v1/me/export"


def a_token(label: str = "") -> str:
    """A token shaped like Firebase's: about 160 characters."""
    return f"fMEP{label}{uuid.uuid4().hex}:APA91bH-{uuid.uuid4().hex}{uuid.uuid4().hex}"


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


class Person:
    def __init__(self, client: TestClient, sender: FakeOtpSender) -> None:
        tokens = log_in(client, sender)
        self.access = tokens["access_token"]
        self.refresh = tokens["refresh_token"]
        self.account_id = decode_access_token(self.access, FIXED_NOW).account_id
        self.headers = {"Authorization": f"Bearer {self.access}"}


@pytest.fixture
def person(client, sender) -> Person:
    return Person(client, sender)


def register(client, who: Person, token: str, **fields):
    return client.put(
        URL,
        json={"token": token, "platform": "android", **fields},
        headers=who.headers,
    )


def tokens_of(db, account_id) -> set[str]:
    return set(
        db.scalars(select(DeviceToken.token).where(DeviceToken.account_id == account_id))
    )


# --- registering -------------------------------------------------------------------------


def test_a_phone_is_registered_and_its_token_never_returned(client, db, person):
    token = a_token()

    response = register(client, person, token, app_version="1.4.0 (212)")

    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == {"id", "platform", "app_version", "last_seen_at", "created_at"}
    assert (body["platform"], body["app_version"]) == ("android", "1.4.0 (212)")
    assert token not in response.text
    assert tokens_of(db, person.account_id) == {token}


def test_registering_again_refreshes_the_same_phone(client, db, clock, person):
    token = a_token()
    first = register(client, person, token).json()
    clock.now += timedelta(minutes=5)  # inside the 15-minute access token

    again = register(client, person, token, app_version="1.5.0").json()

    assert again["id"] == first["id"]
    assert again["last_seen_at"] > first["last_seen_at"]
    assert again["app_version"] == "1.5.0"
    assert (
        db.scalar(select(func.count()).where(DeviceToken.account_id == person.account_id))
        == 1
    )


def test_a_phone_handed_on_stops_getting_the_last_persons_notifications(
    client, db, sender, person
):
    token = a_token()
    register(client, person, token)
    next_owner = Person(client, sender)

    response = register(client, next_owner, token)

    assert response.status_code == 200
    assert tokens_of(db, person.account_id) == set()
    assert tokens_of(db, next_owner.account_id) == {token}


def test_each_account_keeps_its_most_recently_seen_phones(client, db, clock, person):
    tokens = [a_token(str(n)) for n in range(MAX_DEVICES_PER_ACCOUNT + 2)]
    for token in tokens:
        clock.now += timedelta(minutes=1)
        assert register(client, person, token).status_code == 200

    assert tokens_of(db, person.account_id) == set(tokens[2:])


def test_another_accounts_phones_are_untouched_by_the_cap(
    client, db, clock, sender, person
):
    other = Person(client, sender)
    kept = a_token("other")
    register(client, other, kept)
    for n in range(MAX_DEVICES_PER_ACCOUNT + 1):
        clock.now += timedelta(minutes=1)
        register(client, person, a_token(str(n)))

    assert tokens_of(db, other.account_id) == {kept}


@pytest.mark.parametrize(
    "body",
    [
        {"token": "too-short", "platform": "android"},
        {"token": "x" * 1025, "platform": "android"},
        {"token": "has spaces " + "x" * 40, "platform": "android"},
        {"token": "x" * 64, "platform": "web"},
        {"token": "x" * 64},
        {"token": "x" * 64, "platform": "ios", "app_version": ""},
        {"token": "x" * 64, "platform": "ios", "extra": 1},
    ],
)
def test_a_malformed_registration_is_refused(client, person, body):
    response = client.put(URL, json=body, headers=person.headers)

    assert response.status_code == 422


@pytest.mark.parametrize("platform", ["android", "ios", "ios_live_activity"])
def test_every_platform_is_accepted(client, person, platform):
    hex_token = uuid.uuid4().hex * 2  # Apple's: 64 hex digits

    response = register(client, person, hex_token, platform=platform)

    assert response.status_code == 200
    assert response.json()["platform"] == platform


def test_it_needs_a_login(client):
    assert (
        client.put(URL, json={"token": a_token(), "platform": "ios"}).status_code == 401
    )


def test_registering_is_rate_limited(client, person):
    for _ in range(20):
        assert register(client, person, a_token()).status_code == 200

    response = register(client, person, a_token())

    assert response.status_code == 429
    assert response.json()["code"] == "rate_limited"


# --- unregistering -----------------------------------------------------------------------


def test_a_phone_is_unregistered_by_its_id(client, db, person):
    device_id = register(client, person, a_token()).json()["id"]

    response = client.delete(f"{URL}/{device_id}", headers=person.headers)

    assert response.status_code == 204
    assert tokens_of(db, person.account_id) == set()


def test_another_accounts_phone_is_not_found(client, db, sender, person):
    token = a_token()
    device_id = register(client, person, token).json()["id"]
    stranger = Person(client, sender)

    response = client.delete(f"{URL}/{device_id}", headers=stranger.headers)

    assert response.status_code == 404
    assert response.json()["code"] == "device_not_found"
    assert tokens_of(db, person.account_id) == {token}


def test_an_unknown_phone_is_not_found(client, person):
    response = client.delete(f"{URL}/{uuid.uuid4()}", headers=person.headers)

    assert response.status_code == 404


def test_a_malformed_device_id_is_refused(client, person):
    assert client.delete(f"{URL}/not-a-uuid", headers=person.headers).status_code == 422


def test_unregistering_needs_a_login(client):
    assert client.delete(f"{URL}/{uuid.uuid4()}").status_code == 401


# --- logging out -------------------------------------------------------------------------


def test_logging_out_of_a_phone_stops_its_notifications(client, db, person):
    here, elsewhere = a_token("here"), a_token("elsewhere")
    register(client, person, here)
    register(client, person, elsewhere)

    response = client.post(
        LOGOUT_URL, json={"refresh_token": person.refresh, "device_token": here}
    )

    assert response.status_code == 204
    assert tokens_of(db, person.account_id) == {elsewhere}


def test_logging_out_cannot_remove_another_accounts_phone(client, db, sender, person):
    theirs = a_token("theirs")
    other = Person(client, sender)
    register(client, other, theirs)

    client.post(
        LOGOUT_URL, json={"refresh_token": person.refresh, "device_token": theirs}
    )

    assert tokens_of(db, other.account_id) == {theirs}


def test_logging_out_without_a_token_keeps_the_phones(client, db, person):
    token = a_token()
    register(client, person, token)

    client.post(LOGOUT_URL, json={"refresh_token": person.refresh})

    assert tokens_of(db, person.account_id) == {token}


def test_logging_out_everywhere_stops_every_phone(client, db, person):
    for n in range(3):
        register(client, person, a_token(str(n)))

    response = client.post("/api/v1/auth/logout-all", headers=person.headers)

    assert response.status_code == 200
    assert tokens_of(db, person.account_id) == set()


# --- what the person can see -------------------------------------------------------------


def test_the_export_lists_each_phone_without_its_token(client, person):
    token = a_token()
    register(client, person, token, app_version="1.4.0")

    response = client.get(EXPORT_URL, headers=person.headers)

    devices = response.json()["data"]["devices"]
    assert [d["platform"] for d in devices] == ["android"]
    assert devices[0]["app_version"] == "1.4.0"
    assert token not in response.text
