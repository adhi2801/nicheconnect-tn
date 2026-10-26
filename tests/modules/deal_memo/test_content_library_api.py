"""A brand's content library (item 70, D-132).

The rules worth proving: only the brand's own approved posts appear, each
with the window its accepted memo sealed; approval by the clock counts
without anyone having opened the deal; and the SQL filter says exactly what
`content_rights.rights_state` says. Two brands and several deals in every
test that filters (testing.md section 2).
"""

from datetime import timedelta

import pytest

from app.core.clock import india_date
from app.modules.deal_memo.content_library_router import READ_LIMIT
from app.modules.deal_memo.content_rights import rights_state
from tests.deal_flow import LINK, MEMOS_URL, User, accepted_memo, brand_user, creator_user
from tests.query_counts import queries_for

URL = "/api/v1/brands/me/content"


@pytest.fixture
def brand(db, clock) -> User:
    return brand_user(db, clock)


def submitted(client, brand: User, creator: User, **memo) -> tuple[str, str]:
    memo_id = accepted_memo(client, brand, creator, **memo)
    proof = client.post(
        f"{MEMOS_URL}/{memo_id}/proof",
        json={"content_url": LINK, "format": "reel", "disclosure_confirmed": True},
        headers=creator.headers,
    )
    assert proof.status_code == 201, proof.text
    return memo_id, proof.json()["id"]


def approved(client, db, clock, brand: User, **memo) -> tuple[str, str]:
    creator = creator_user(db, clock)
    memo_id, proof_id = submitted(client, brand, creator, **memo)
    done = client.post(
        f"{MEMOS_URL}/{memo_id}/proof/{proof_id}/approve", headers=brand.headers
    )
    assert done.status_code == 200, done.text
    return memo_id, proof_id


def library(client, brand: User, **params) -> dict:
    response = client.get(URL, params=params, headers=brand.headers)
    assert response.status_code == 200, response.text
    return response.json()


def proof_ids(body: dict) -> list[str]:
    return [item["proof_id"] for item in body["items"]]


def test_an_approved_post_appears_with_its_window(client, db, clock, brand):
    memo_id, proof_id = approved(client, db, clock, brand, usage_rights_days=90)

    (item,) = library(client, brand)["items"]

    assert (item["proof_id"], item["deal_memo_id"]) == (proof_id, memo_id)
    assert item["usage_rights_days"] == 90
    assert (
        item["rights_until"] == (india_date(clock.now) + timedelta(days=90)).isoformat()
    )
    assert item["rights_state"] == "active"
    assert (item["auto_approved"], item["content_url"]) == (False, LINK)
    assert item["campaign_title"] == "Pongal sweets launch"


def test_a_memo_without_days_reads_not_agreed(client, db, clock, brand):
    approved(client, db, clock, brand)

    (item,) = library(client, brand)["items"]

    assert (item["usage_rights_days"], item["rights_until"], item["rights_state"]) == (
        None,
        None,
        "not_agreed",
    )


def test_only_the_brands_own_approved_posts_appear(client, db, clock, brand):
    mine = approved(client, db, clock, brand, usage_rights_days=30)[1]
    other = brand_user(db, clock)
    theirs = approved(client, db, clock, other, usage_rights_days=30)[1]
    submitted(client, brand, creator_user(db, clock))  # waiting, not approved

    assert proof_ids(library(client, brand)) == [mine]
    assert proof_ids(library(client, other)) == [theirs]


def test_approval_by_the_clock_counts_without_anyone_opening_the_deal(
    client, db, clock, brand
):
    _, proof_id = submitted(client, brand, creator_user(db, clock), usage_rights_days=30)
    assert library(client, brand)["items"] == []

    clock.advance(timedelta(days=8))  # past the 7-day review window

    (item,) = library(client, brand)["items"]
    assert (item["proof_id"], item["auto_approved"]) == (proof_id, True)


def test_each_state_filters_to_exactly_its_posts(client, db, clock, brand):
    windows = {"lapsed": 5, "lapsing": 40, "active": 400, "not_agreed": None}
    made = {}
    for state, window in windows.items():
        fields = {} if window is None else {"usage_rights_days": window}
        made[state] = approved(client, db, clock, brand, **fields)[1]
    clock.advance(timedelta(days=20))

    for state, proof_id in made.items():
        assert proof_ids(library(client, brand, rights_state=state)) == [proof_id], state
    assert len(library(client, brand)["items"]) == 4


def test_the_sql_filter_says_what_the_rule_says(client, db, clock, brand, unlimited):
    """Windows around every edge, asked both ways, today and a month on.

    Approved at 20:00 UTC, 01:30 the next day in Tamil Nadu, so a window
    counted from the wrong day's start lands on the wrong side of an edge."""
    clock.now = clock.now.replace(hour=20, minute=0)
    for window in (1, 2, 29, 30, 31, 32, 60, None):
        fields = {} if window is None else {"usage_rights_days": window}
        approved(client, db, clock, brand, **fields)

    for advance in (0, 1, 30):
        clock.advance(timedelta(days=advance))
        everything = library(client, brand, limit=100)["items"]
        today = india_date(clock.now)
        for item in everything:
            until = item["rights_until"]
            expected = rights_state(
                None if until is None else type(today).fromisoformat(until), today
            )
            assert item["rights_state"] == expected
        for state in ("active", "lapsing", "lapsed", "not_agreed"):
            filtered = proof_ids(library(client, brand, rights_state=state, limit=100))
            assert filtered == [
                i["proof_id"] for i in everything if i["rights_state"] == state
            ]


def test_pages_have_no_gaps_or_repeats(client, db, clock, brand):
    expected = []
    for _ in range(5):
        expected.insert(0, approved(client, db, clock, brand)[1])
        clock.advance(timedelta(minutes=1))

    seen, cursor = [], None
    while True:
        params = {"limit": 2} | ({"cursor": cursor} if cursor else {})
        body = library(client, brand, **params)
        seen += proof_ids(body)
        cursor = body["next_cursor"]
        if cursor is None:
            break

    assert seen == expected


def test_a_long_page_costs_the_same_queries_as_a_short_one(client, db, clock):
    short, long = brand_user(db, clock), brand_user(db, clock)
    approved(client, db, clock, short, usage_rights_days=30)
    for _ in range(6):
        approved(client, db, clock, long, usage_rights_days=30)
    library(client, short)  # the first read after a commit opens the test's savepoint

    assert queries_for(client, URL, long.headers) == queries_for(
        client, URL, short.headers
    )


def test_creators_keep_no_library(client, db, clock):
    assert client.get(URL, headers=creator_user(db, clock).headers).status_code == 403


def test_the_library_needs_a_login(client):
    assert client.get(URL).status_code == 401


@pytest.mark.parametrize(
    "params", [{"rights_state": "forever"}, {"limit": 0}, {"cursor": "nope"}]
)
def test_bad_parameters_are_refused(client, brand, params):
    assert client.get(URL, params=params, headers=brand.headers).status_code == 422


def test_it_is_rate_limited(client, brand):
    for _ in range(int(READ_LIMIT.split()[0])):
        assert client.get(URL, headers=brand.headers).status_code == 200

    assert client.get(URL, headers=brand.headers).status_code == 429
