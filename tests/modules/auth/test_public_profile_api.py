"""The public Creator Passport: readable by anyone, and carrying nothing private."""

import uuid
from collections.abc import Iterator
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.core.rate_limit import limiter
from app.db.session import get_db
from app.main import app
from app.modules.auth import public_router
from app.modules.auth.dependencies import get_now
from app.modules.auth.models.creator import Creator
from tests.factories import FIXED_NOW, build_creator

URL = "/api/v1/creators/by-handle"
# The whole agreed contract. If this list changes, the change was deliberate.
PUBLIC_FIELDS = {
    "id",
    "handle",
    "display_name",
    "city",
    "niches",
    "languages",
    "bio",
    "member_since",
}


@pytest.fixture
def client(db) -> Iterator[TestClient]:
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_now] = lambda: FIXED_NOW
    limiter.reset()
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
        limiter.reset()


def make_creator(db, **overrides) -> Creator:
    """A creator who has published their Passport.

    Published on purpose: these tests are about the public page, and nobody
    appears on it until they have chosen to (D-036). The tests that cover
    *not* having chosen pass `passport_published_at=None` explicitly.
    """
    overrides.setdefault("passport_published_at", FIXED_NOW)
    creator = build_creator(db, **overrides)
    db.add(creator)
    db.flush()
    return creator


def assert_problem(response, status: int, code: str) -> dict:
    assert response.status_code == status, response.text
    assert response.headers["content-type"] == "application/problem+json"
    body = response.json()
    assert body["code"] == code
    return body


# --- reading it -----------------------------------------------------------


def test_anyone_can_read_a_profile_without_logging_in(client, db):
    creator = make_creator(db, handle="priya.eats", city="Coimbatore")

    response = client.get(f"{URL}/priya.eats")

    assert response.status_code == 200
    body = response.json()
    assert body["handle"] == "priya.eats"
    assert body["display_name"] == creator.display_name
    assert body["city"] == "Coimbatore"
    assert body["niches"] == creator.niches
    assert body["member_since"] == "2026-09"


def test_the_response_carries_exactly_the_agreed_fields(client, db):
    """A new column must never appear here by accident."""
    make_creator(db, handle="priya.eats")

    body = client.get(f"{URL}/priya.eats").json()

    assert set(body) == PUBLIC_FIELDS


def test_nothing_private_is_ever_in_the_response(client, db):
    creator = make_creator(db, handle="priya.eats")
    from app.modules.auth.models.account import Account

    account = db.get(Account, creator.account_id)

    text = client.get(f"{URL}/priya.eats").text

    assert account.phone not in text
    assert str(creator.account_id) not in text
    for forbidden in ("phone", "email", "account_id", "updated_at"):
        assert forbidden not in text


@pytest.mark.parametrize("typed", ["Priya.Eats", "@priya.eats", "PRIYA.EATS", " priya.eats "])
def test_handles_are_matched_however_they_are_typed(client, db, typed):
    make_creator(db, handle="priya.eats")

    assert client.get(f"{URL}/{typed}").status_code == 200


def test_an_unknown_handle_is_not_found(client, db):
    make_creator(db, handle="priya.eats")

    assert_problem(client.get(f"{URL}/someone.else"), 404, "profile_not_found")


@pytest.mark.parametrize("handle", ["ab", "has space", "x" * 40, "!!"])
def test_an_impossible_handle_is_simply_not_found(client, db, handle):
    """No hint about what a valid handle looks like, and no stack trace."""
    assert_problem(client.get(f"{URL}/{handle}"), 404, "profile_not_found")


def test_two_creators_do_not_leak_into_each_other(client, db):
    make_creator(db, handle="priya.eats", city="Coimbatore")
    make_creator(db, handle="ravi.tech", city="Madurai", display_name="Ravi Tech")

    first = client.get(f"{URL}/priya.eats").json()
    second = client.get(f"{URL}/ravi.tech").json()

    assert first["city"] == "Coimbatore"
    assert second["city"] == "Madurai"
    assert first["id"] != second["id"]


# --- caching --------------------------------------------------------------


def test_a_profile_is_cacheable_for_five_minutes(client, db):
    make_creator(db, handle="priya.eats")

    response = client.get(f"{URL}/priya.eats")

    assert response.headers["cache-control"] == "public, max-age=300"
    assert response.headers["etag"].startswith('"')


def test_an_unchanged_profile_costs_nothing_to_re_read(client, db):
    make_creator(db, handle="priya.eats")
    etag = client.get(f"{URL}/priya.eats").headers["etag"]

    again = client.get(f"{URL}/priya.eats", headers={"If-None-Match": etag})

    assert again.status_code == 304
    assert again.content == b""
    assert again.headers["etag"] == etag


def test_editing_the_profile_changes_the_etag(client, db):
    creator = make_creator(db, handle="priya.eats")
    first = client.get(f"{URL}/priya.eats").headers["etag"]

    creator.bio = "Now covering Madurai too."
    creator.updated_at = FIXED_NOW + timedelta(hours=1)
    db.flush()
    second = client.get(f"{URL}/priya.eats")

    assert second.headers["etag"] != first
    assert second.status_code == 200
    assert second.json()["bio"] == "Now covering Madurai too."


def test_an_old_etag_gets_the_new_profile(client, db):
    creator = make_creator(db, handle="priya.eats")
    stale = client.get(f"{URL}/priya.eats").headers["etag"]
    creator.city = "Madurai"
    creator.updated_at = FIXED_NOW + timedelta(hours=1)
    db.flush()

    response = client.get(f"{URL}/priya.eats", headers={"If-None-Match": stale})

    assert response.status_code == 200
    assert response.json()["city"] == "Madurai"


# --- the publication switch ----------------------------------------------


def test_a_creator_who_has_not_published_is_not_found(client, db):
    """Not "private", not "hidden" — simply not there, and indistinguishable
    from a handle that was never taken."""
    make_creator(db, handle="priya.eats", passport_published_at=None)

    assert_problem(client.get(f"{URL}/priya.eats"), 404, "profile_not_found")


def test_nobody_is_published_until_they_choose(db):
    """The default, and the whole point of D-036.

    Somebody who signed up to browse campaigns is not findable by strangers.
    """
    creator = build_creator(db, handle=f"seam{uuid.uuid4().hex[:8]}")

    assert creator.passport_published_at is None
    assert public_router.passport_is_public(creator) is False


def test_choosing_to_publish_makes_the_page_answer(db):
    creator = build_creator(
        db, handle=f"seam{uuid.uuid4().hex[:8]}", passport_published_at=FIXED_NOW
    )

    assert public_router.passport_is_public(creator) is True


def test_an_unpublished_profile_cannot_be_told_apart_from_a_missing_one(client, db):
    """A 404 either way, so nobody can use this page to work out whether a
    handle belongs to somebody who chose not to be listed."""
    make_creator(db, handle="priya.eats", passport_published_at=None)

    hidden = client.get(f"{URL}/priya.eats")
    absent = client.get(f"{URL}/nobody.here")

    assert hidden.status_code == absent.status_code == 404
    assert hidden.json()["code"] == absent.json()["code"]


# --- limits ---------------------------------------------------------------


def test_the_public_page_is_rate_limited(client, db):
    make_creator(db, handle="priya.eats")
    for _ in range(60):
        client.get(f"{URL}/priya.eats")

    response = client.get(f"{URL}/priya.eats")

    assert_problem(response, 429, "rate_limited")
    assert response.headers["retry-after"] == "60"
