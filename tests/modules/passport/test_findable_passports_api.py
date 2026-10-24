"""Published Passports offered to search engines (item 85, D-121), through the API.

The feed for the website's sitemap, each Passport's ProfilePage structured
data, both behind PASSPORT_INDEXING, and no API answer indexed itself.
"""

import uuid
from collections.abc import Iterator
from datetime import datetime, timedelta

import pytest

from app.core.config import settings
from app.modules.auth.models.account import Account
from app.modules.passport import passport_service
from tests.deal_flow import User
from tests.factories import FIXED_NOW, create_account
from tests.modules.admin.test_takedowns_api import withhold
from tests.modules.passport.test_public_profile_api import (
    add_channel,
    add_package,
    make_creator,
)
from tests.query_counts import queries_for

FEED_URL = "/api/v1/creators/indexable"
PASSPORT_URL = "/api/v1/creators/by-handle"


@pytest.fixture
def indexing(monkeypatch) -> Iterator[None]:
    monkeypatch.setattr(settings, "passport_indexing", True)
    yield


def feed(client, **params) -> dict:
    response = client.get(FEED_URL, params=params)
    assert response.status_code == 200, response.text
    return response.json()


def handles(client, **params) -> list[str]:
    return [item["handle"] for item in feed(client, **params)["items"]]


def creator(db, label: str, **overrides):
    return make_creator(db, handle=f"{label}{uuid.uuid4().hex[:10]}", **overrides)


# --- off until the publish notice says so -------------------------------------------------


def test_while_switched_off_the_feed_is_empty_and_no_structured_data(client, db):
    shown = creator(db, "off")

    assert feed(client) == {"items": [], "next_cursor": None}
    passport = client.get(f"{PASSPORT_URL}/{shown.handle}").json()
    assert passport["structured_data"] is None


# --- the feed -----------------------------------------------------------------------------


def test_the_feed_lists_exactly_the_passports_anyone_may_read(
    client, db, clock, indexing
):
    published = creator(db, "pub")
    unpublished = creator(db, "unpub", passport_published_at=None)
    suspended = creator(db, "susp")
    account = db.get_one(Account, suspended.account_id)
    account.suspended_at = FIXED_NOW
    account.suspension_reason = "fake_profile"
    withheld = creator(db, "held")
    db.flush()
    admin = User(create_account(db, "admin").id, "admin", clock)
    assert withhold(client, admin, "creator", withheld.id).status_code == 201

    listed = set(handles(client, limit=100))

    assert published.handle in listed
    assert not listed & {unpublished.handle, suspended.handle, withheld.handle}


def test_pages_have_no_gaps_or_repeats(client, db, indexing):
    made = {creator(db, f"page{n}").handle for n in range(5)}

    seen: list[str] = []
    cursor = None
    while True:
        params = {"limit": 2, **({"cursor": cursor} if cursor else {})}
        body = feed(client, **params)
        seen += [item["handle"] for item in body["items"]]
        cursor = body["next_cursor"]
        if cursor is None:
            break

    assert made <= set(seen)
    assert len(seen) == len(set(seen))


def test_last_modified_follows_what_readers_see(client, db, indexing):
    shown = creator(
        db,
        "lm",
        updated_at=FIXED_NOW - timedelta(days=9),
        passport_published_at=FIXED_NOW - timedelta(days=9),
    )
    channel = add_channel(db, shown)
    channel.updated_at = FIXED_NOW - timedelta(days=2)
    hidden_package = add_package(db, shown)
    hidden_package.updated_at = FIXED_NOW
    db.flush()

    [item] = [i for i in feed(client, limit=100)["items"] if i["handle"] == shown.handle]

    # The package's change is not counted while prices are not public.
    assert item["last_modified"].startswith(
        (FIXED_NOW - timedelta(days=2)).isoformat()[:19]
    )


def test_the_feed_and_the_passport_agree_on_when_it_changed(client, db, indexing):
    shown = creator(db, "agree", rate_card_public_at=FIXED_NOW - timedelta(days=1))
    channel = add_channel(db, shown)
    channel.updated_at = FIXED_NOW - timedelta(days=3)
    package = add_package(db, shown)
    package.updated_at = FIXED_NOW - timedelta(hours=5)
    db.flush()

    [item] = [i for i in feed(client, limit=100)["items"] if i["handle"] == shown.handle]
    passport = client.get(f"{PASSPORT_URL}/{shown.handle}").json()

    assert datetime.fromisoformat(item["last_modified"]) == datetime.fromisoformat(
        passport["structured_data"]["dateModified"]
    )


def test_a_long_feed_costs_the_same_queries_as_a_short_one(client, db, indexing):
    creator(db, "qc")
    short = queries_for(client, FEED_URL, {}, params={"limit": 100})
    for n in range(8):
        add_channel(db, creator(db, f"qc{n}"))

    assert queries_for(client, FEED_URL, {}, params={"limit": 100}) == short


def test_the_feed_is_cached_and_answers_304_when_unchanged(client, db, indexing):
    creator(db, "etag")
    first = client.get(FEED_URL)
    etag = first.headers["etag"]

    again = client.get(FEED_URL, headers={"If-None-Match": etag})

    assert first.headers["cache-control"] == "public, max-age=300"
    assert again.status_code == 304


@pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 101}, {"cursor": "nope"}])
def test_a_bad_page_request_is_refused(client, indexing, params):
    assert client.get(FEED_URL, params=params).status_code == 422


# --- structured data ----------------------------------------------------------------------


def test_a_passport_carries_profile_page_markup_of_published_fields_only(
    client, db, indexing
):
    shown = creator(db, "ld", bio="Coimbatore street food, every weekend.")
    add_channel(db, shown, "instagram")
    add_channel(db, shown, "youtube")

    data = client.get(f"{PASSPORT_URL}/{shown.handle}").json()["structured_data"]

    assert data["@context"] == "https://schema.org"
    assert data["@type"] == "ProfilePage"
    person = data["mainEntity"]
    assert person == {
        "@type": "Person",
        "name": shown.display_name,
        "alternateName": shown.handle,
        "identifier": str(shown.id),
        "description": "Coimbatore street food, every weekend.",
        "sameAs": sorted(person["sameAs"]),
    }
    assert set(person["sameAs"]) == {
        f"https://instagram.com/{shown.handle}",
        f"https://youtube.com/{shown.handle}",
    }
    text = str(data)
    assert "48213" not in text and "9731" not in text


def test_a_passport_without_a_bio_or_channels_leaves_them_out(client, db, indexing):
    shown = creator(db, "bare", bio=None)

    person = client.get(f"{PASSPORT_URL}/{shown.handle}").json()["structured_data"][
        "mainEntity"
    ]

    assert "description" not in person and "sameAs" not in person


# --- never indexed itself -----------------------------------------------------------------


@pytest.mark.parametrize(
    "url", ["/healthz", FEED_URL, f"{PASSPORT_URL}/nobody-here", "/nope"]
)
def test_no_api_answer_is_indexed_itself(client, url):
    assert client.get(url).headers["x-robots-tag"] == "noindex"


def test_the_service_offers_nothing_while_switched_off(db):
    creator(db, "svc")

    assert passport_service.indexable_passports(db, limit=10, cursor=None).rows == []
