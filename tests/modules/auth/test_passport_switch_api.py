"""Turning the public Creator Passport on and off.

Being findable by the whole internet is a choice somebody makes, not a
setting they inherit. These tests are mostly about that being true.
"""

from collections.abc import Iterator
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.core.rate_limit import limiter
from app.db.session import get_db
from app.main import app
from app.modules.auth.dependencies import get_now
from app.modules.auth.tokens import create_access_token
from tests.factories import FIXED_NOW, create_account

CREATOR_URL = "/api/v1/creators/me"
PUBLISH_URL = f"{CREATOR_URL}/passport/publish"
UNPUBLISH_URL = f"{CREATOR_URL}/passport/unpublish"
PUBLIC_URL = "/api/v1/creators/by-handle"
HANDLE = "priya.eats"


class Clock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def advance(self, delta: timedelta) -> None:
        self.now += delta


@pytest.fixture
def clock() -> Clock:
    return Clock(FIXED_NOW)


@pytest.fixture
def client(db, clock) -> Iterator[TestClient]:
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_now] = lambda: clock.now
    limiter.reset()
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
        limiter.reset()


class User:
    """A signed-in account. `headers` mints a token for the clock's current
    time, so a test that moves days forward stays signed in, as a real app
    would by refreshing."""

    def __init__(self, account_id, role: str, clock: Clock) -> None:
        self.account_id = account_id
        self.role = role
        self.clock = clock

    @property
    def headers(self) -> dict[str, str]:
        token, _ = create_access_token(self.account_id, self.role, self.clock.now)
        return {"Authorization": f"Bearer {token}"}


def user_for(db, clock, role: str) -> User:
    return User(create_account(db, role).id, role, clock)


@pytest.fixture
def creator(client, db, clock) -> User:
    """A signed-in creator with a profile, not published."""
    user = user_for(db, clock, "creator")
    created = client.post(
        CREATOR_URL,
        json={
            "display_name": "Priya Eats",
            "handle": HANDLE,
            "city": "Coimbatore",
            "niches": ["food"],
            "bio": "Street food across Tamil Nadu.",
        },
        headers=user.headers,
    )
    assert created.status_code == 201, created.text
    return user


# --- the default ----------------------------------------------------------


def test_a_new_profile_is_not_published(client, creator):
    body = client.get(CREATOR_URL, headers=creator.headers).json()

    assert body["passport_published_at"] is None


def test_a_new_profile_is_not_findable_by_strangers(client, creator):
    """Somebody who signed up to browse campaigns has not asked to be found."""
    assert client.get(f"{PUBLIC_URL}/{HANDLE}").status_code == 404


# --- turning it on --------------------------------------------------------


def test_publishing_makes_the_page_answer(client, creator):
    published = client.post(PUBLISH_URL, headers=creator.headers)

    assert published.status_code == 200, published.text
    assert published.json()["passport_published_at"] is not None
    assert client.get(f"{PUBLIC_URL}/{HANDLE}").status_code == 200


def test_the_public_page_still_carries_nothing_private(client, db, creator):
    from sqlalchemy import select

    from app.modules.auth.models.account import Account

    client.post(PUBLISH_URL, headers=creator.headers)
    phones = db.scalars(select(Account.phone)).all()

    text = client.get(f"{PUBLIC_URL}/{HANDLE}").text

    for phone in phones:
        assert phone not in text
    assert "passport_published_at" not in text


def test_publishing_twice_keeps_the_day_they_first_chose(client, creator, clock):
    """The timestamp is the consent. A second tap on a slow connection is
    not a second decision."""
    first = client.post(PUBLISH_URL, headers=creator.headers).json()["passport_published_at"]
    clock.advance(timedelta(days=3))

    again = client.post(PUBLISH_URL, headers=creator.headers).json()[
        "passport_published_at"
    ]

    assert again == first


# --- turning it off -------------------------------------------------------


def test_unpublishing_takes_the_page_down_at_once(client, creator):
    client.post(PUBLISH_URL, headers=creator.headers)

    client.post(UNPUBLISH_URL, headers=creator.headers)

    assert client.get(f"{PUBLIC_URL}/{HANDLE}").status_code == 404


def test_withdrawing_is_never_refused(client, creator):
    """Somebody who wants to stop being findable should not have to argue."""
    response = client.post(UNPUBLISH_URL, headers=creator.headers)

    assert response.status_code == 200
    assert response.json()["passport_published_at"] is None


def test_the_profile_itself_survives_being_unpublished(client, creator):
    client.post(PUBLISH_URL, headers=creator.headers)
    client.post(UNPUBLISH_URL, headers=creator.headers)

    body = client.get(CREATOR_URL, headers=creator.headers).json()

    assert body["handle"] == HANDLE
    assert body["display_name"] == "Priya Eats"


def test_it_can_be_turned_back_on(client, creator, clock):
    client.post(PUBLISH_URL, headers=creator.headers)
    client.post(UNPUBLISH_URL, headers=creator.headers)
    clock.advance(timedelta(days=1))

    client.post(PUBLISH_URL, headers=creator.headers)

    assert client.get(f"{PUBLIC_URL}/{HANDLE}").status_code == 200


# --- who may flip it ------------------------------------------------------


def test_only_the_creator_themselves_can_publish(client, db, clock):
    """There is no identifier in the path, so there is nobody else to name."""
    brand = user_for(db, clock, "brand")

    response = client.post(PUBLISH_URL, headers=brand.headers)

    assert response.status_code == 403


def test_it_needs_a_login(client):
    assert client.post(PUBLISH_URL).status_code == 401
    assert client.post(UNPUBLISH_URL).status_code == 401


def test_there_is_nothing_to_publish_without_a_profile(client, db, clock):
    user = user_for(db, clock, "creator")

    response = client.post(PUBLISH_URL, headers=user.headers)

    assert response.status_code == 404
