"""The pre-deal check through the API (item 133, D-182).

Each side of a deal reads facts about the other from our records: never a
score, never a refusal. Every test that reads records builds two brands and
two creators (testing.md section 2), so a count tied to the wrong side, or
to every deal rather than this pair's, cannot pass by luck.
"""

import uuid
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app.core.clock import india_date
from app.modules.auth.models.account import Account
from app.modules.deal_memo.check_router import READ_LIMIT
from tests.deal_flow import (
    LINK,
    MEMOS_URL,
    PAYMENT_REFERENCE,
    User,
    accepted_memo,
    brand_user,
    creator_user,
    finish_deal,
)
from tests.factories import create_account
from tests.modules.admin.test_takedowns_api import creator_id_of, withhold
from tests.modules.me.test_team_api import join
from tests.modules.passport.test_media_kit_api import add_channel, profile_of
from tests.modules.profiles.test_connection_model import connection
from tests.query_counts import queries_for

REASON = "The payment was marked sent on 8 September but nothing has reached my account."
NO_DISPUTES = {
    "open": 0,
    "unresolved": 0,
    "resolved_paid": 0,
    "resolved_withdrawn": 0,
    "resolved_informally": 0,
}


def check_url(memo_id: str) -> str:
    return f"{MEMOS_URL}/{memo_id}/check"


def read(client: TestClient, memo_id: str, user: User) -> dict:
    response = client.get(check_url(memo_id), headers=user.headers)
    assert response.status_code == 200, response.text
    return response.json()


def profile_id(client: TestClient, user: User) -> str:
    path = "/api/v1/brands/me" if user.role == "brand" else "/api/v1/creators/me"
    return client.get(path, headers=user.headers).json()["id"]


def sent_memo(client: TestClient, brand: User, creator: User) -> str:
    """A memo sent and waiting for the creator's answer: the moment the check is for."""
    memo_id = draft_memo(client, brand, creator)
    sent = client.post(f"{MEMOS_URL}/{memo_id}/send", headers=brand.headers)
    assert sent.status_code == 200, sent.text
    return memo_id


def draft_memo(client: TestClient, brand: User, creator: User) -> str:
    """A memo the brand has written and not yet sent."""
    campaign_id = client.post(
        "/api/v1/campaigns",
        json={
            "title": "Diwali sweets launch",
            "description": "Two reels featuring our new sweet box.",
            "campaign_type": "paid",
            "budget_min_paise": 500_000,
            "budget_max_paise": 1_500_000,
            "cities": ["Madurai"],
            "niches": ["food"],
            "deliverables": "2 Instagram reels",
        },
        headers=brand.headers,
    ).json()["id"]
    client.post(f"/api/v1/campaigns/{campaign_id}/publish", headers=brand.headers)
    application_id = client.post(
        f"/api/v1/campaigns/{campaign_id}/applications",
        json={"pitch": "I cover food in Madurai for local families, in Tamil."},
        headers=creator.headers,
    ).json()["id"]
    for step in ("shortlist", "accept"):
        client.post(
            f"/api/v1/applications/{application_id}/{step}", headers=brand.headers
        )
    made = client.post(
        f"{MEMOS_URL}/for-application/{application_id}",
        json={
            "deliverables": "2 Instagram reels.",
            "fee_amount_paise": 700_000,
            "content_due_on": "2026-12-31",
        },
        headers=brand.headers,
    )
    assert made.status_code == 201, made.text
    return str(made.json()["id"])


def approved(client: TestClient, brand: User, creator: User) -> str:
    """An agreed deal with its work approved: its payment now owed."""
    memo_id = accepted_memo(client, brand, creator)
    proof_id = client.post(
        f"{MEMOS_URL}/{memo_id}/proof",
        json={"content_url": LINK, "format": "reel", "disclosure_confirmed": True},
        headers=creator.headers,
    ).json()["id"]
    done = client.post(
        f"{MEMOS_URL}/{memo_id}/proof/{proof_id}/approve", headers=brand.headers
    )
    assert done.status_code == 200, done.text
    return memo_id


def marked_paid(client: TestClient, brand: User, creator: User) -> str:
    """An agreed deal with its work approved and its payment marked sent."""
    memo_id = approved(client, brand, creator)
    paid = client.post(
        f"{MEMOS_URL}/{memo_id}/payment/mark-paid",
        json={"method": "upi", "reference": PAYMENT_REFERENCE},
        headers=brand.headers,
    )
    assert paid.status_code == 200, paid.text
    return memo_id


def disputed(client: TestClient, brand: User, creator: User) -> str:
    """A deal whose payment went to a dispute, still open."""
    memo_id = marked_paid(client, brand, creator)
    raised = client.post(
        f"{MEMOS_URL}/{memo_id}/payment/dispute",
        json={"reason": REASON},
        headers=creator.headers,
    )
    assert raised.status_code == 201, raised.text
    return memo_id


@pytest.fixture
def brand(db, clock) -> User:
    return brand_user(db, clock)


@pytest.fixture
def creator(db, clock) -> User:
    return creator_user(db, clock)


@pytest.fixture
def other_brand(db, clock) -> User:
    return brand_user(db, clock)


@pytest.fixture
def other_creator(db, clock) -> User:
    return creator_user(db, clock)


# --- what each side reads ------------------------------------------------------------


def test_the_creator_reads_facts_about_the_brand_and_only_this_brand(
    client, db, clock, unlimited, brand, creator, other_brand, other_creator
):
    # The brand's history with another creator counts; another brand's never.
    finish_deal(client, brand, other_creator, accepted_memo(client, brand, other_creator))
    disputed(client, brand, other_creator)
    disputed(client, other_brand, creator)
    finish_deal(client, other_brand, creator, accepted_memo(client, other_brand, creator))
    memo_id = sent_memo(client, brand, creator)

    body = read(client, memo_id, creator)

    assert body["deal_memo_id"] == memo_id
    assert body["as_of"] == india_date(clock.now).isoformat()
    assert body["about_creator"] is None
    about = body["about_brand"]
    assert about["brand_id"] == profile_id(client, brand)
    owner = db.get_one(Account, brand.account_id)
    assert about["account_created_on"] == india_date(owner.created_at).isoformat()
    record = about["payment_record"]
    assert record["brand_id"] == about["brand_id"]
    # One confirmed, one marked paid with its dispute open: both settled as paid.
    assert (record["deals_completed"], record["deals_paid"]) == (2, 2)
    assert record["distinct_creators"] == 1
    assert record["verified_domain"] is None
    assert record["brand_name_flag"] is None
    assert about["disputes"] == {
        "deals_agreed": 2,
        "went_to_dispute": 1,
        "outcomes": NO_DISPUTES | {"open": 1},
    }
    assert about["work_reviewed"] == {
        "examples": 2,
        "median_hours": None,
        "min_examples": 5,
    }


def test_the_brand_reads_facts_about_the_creator_and_only_this_creator(
    client, db, clock, unlimited, brand, creator, other_brand, other_creator
):
    finish_deal(client, other_brand, creator, accepted_memo(client, other_brand, creator))
    disputed(client, other_brand, creator)
    disputed(client, brand, other_creator)
    add_channel(db, profile_of(db, creator), followers=21_400)
    add_channel(db, profile_of(db, other_creator), followers=99_000)
    connection(
        db,
        profile_of(db, creator).id,
        user=f"'{uuid.uuid4().hex}'",
        handle="'madurai.eats'",
        followers="18200",
        as_of="now()",
    )
    memo_id = sent_memo(client, brand, creator)

    body = read(client, memo_id, brand)

    assert body["about_brand"] is None
    about = body["about_creator"]
    assert about["creator_id"] == profile_id(client, creator)
    account = db.get_one(Account, creator.account_id)
    assert about["account_created_on"] == india_date(account.created_at).isoformat()
    assert about["delivery_record"]["deals_completed"] == 2
    assert about["delivery_record"]["distinct_brands"] == 1
    assert about["disputes"] == {
        "deals_agreed": 2,
        "went_to_dispute": 1,
        "outcomes": NO_DISPUTES | {"open": 1},
    }
    assert about["memo_answered"]["examples"] == 2
    assert about["memo_answered"]["median_hours"] is None
    assert about["profile_withheld"] is False
    [channel] = about["channels"]
    assert (channel["followers"], channel["self_reported"]) == (21_400, True)
    [connected] = about["connected_accounts"]
    assert (connected["handle"], connected["verified_followers"]) == (
        "madurai.eats",
        18_200,
    )


def test_a_member_of_the_brands_team_reads_what_the_owner_reads(
    client, db, clock, brand, creator, other_brand
):
    member = join(client, db, clock, brand, "finance")
    outsider = join(client, db, clock, other_brand, "admin")
    memo_id = sent_memo(client, brand, creator)

    assert read(client, memo_id, member) == read(client, memo_id, brand)
    response = client.get(check_url(memo_id), headers=outsider.headers)
    assert (response.status_code, response.json()["code"]) == (404, "memo_not_found")


def test_the_brand_reads_it_on_a_draft_the_creator_cannot_see_yet(client, brand, creator):
    memo_id = draft_memo(client, brand, creator)

    assert read(client, memo_id, brand)["about_creator"] is not None
    response = client.get(check_url(memo_id), headers=creator.headers)
    assert (response.status_code, response.json()["code"]) == (404, "memo_not_found")


# --- not enough to say -----------------------------------------------------------------


def test_below_three_deals_the_shares_are_null_never_zero_and_the_counts_stay(
    client, clock, unlimited, brand, creator, other_brand, other_creator
):
    for _ in range(2):
        finish_deal(client, brand, creator, accepted_memo(client, brand, creator))
        clock.advance(timedelta(hours=1))
    finish_deal(
        client,
        other_brand,
        other_creator,
        accepted_memo(client, other_brand, other_creator),
    )
    owed = approved(client, brand, creator)
    clock.advance(timedelta(hours=1))
    memo_id = sent_memo(client, brand, creator)

    payment = read(client, memo_id, creator)["about_brand"]["payment_record"]
    delivery = read(client, memo_id, brand)["about_creator"]["delivery_record"]

    assert payment["deals_completed"] == 2
    assert payment["paid_on_time_share"] is None
    assert payment["median_days_to_pay"] is None
    assert delivery["deals_completed"] == 3
    assert delivery["delivered_on_time_share"] == 1.0
    assert payment["currently_overdue"] == 0

    paid = client.post(
        f"{MEMOS_URL}/{owed}/payment/mark-paid",
        json={"method": "upi", "reference": PAYMENT_REFERENCE},
        headers=brand.headers,
    )
    assert paid.status_code == 200, paid.text
    payment = read(client, memo_id, creator)["about_brand"]["payment_record"]

    assert payment["deals_completed"] == 3
    assert payment["paid_on_time_share"] == 1.0
    assert payment["median_days_to_pay"] == 0


def test_a_creator_with_no_deals_reads_as_none_and_null(
    client, unlimited, brand, creator, other_creator
):
    # The same brand's deal with another creator is never this creator's.
    finish_deal(client, brand, other_creator, accepted_memo(client, brand, other_creator))
    memo_id = draft_memo(client, brand, creator)

    about = read(client, memo_id, brand)["about_creator"]

    assert about["delivery_record"]["deals_completed"] == 0
    assert about["delivery_record"]["delivered_on_time_share"] is None
    assert about["memo_answered"] == {
        "examples": 0,
        "median_hours": None,
        "min_examples": 5,
    }
    assert about["disputes"] == {
        "deals_agreed": 0,
        "went_to_dispute": 0,
        "outcomes": NO_DISPUTES,
    }
    assert about["channels"] == []


# --- disputes, as how each ended --------------------------------------------------------


def test_each_dispute_is_counted_by_how_it_ended_never_by_who_raised_it(
    client, clock, unlimited, brand, creator, other_brand, other_creator
):
    disputed(client, brand, creator)
    settled = disputed(client, brand, other_creator)
    # Another brand's dispute with the same creator is never this brand's.
    disputed(client, other_brand, creator)
    clock.advance(timedelta(days=1))
    closed = client.post(
        f"{MEMOS_URL}/{settled}/payment/dispute/close",
        json={"outcome": "resolved_paid"},
        headers=brand.headers,
    )
    assert closed.status_code == 200, closed.text
    clock.advance(timedelta(days=31))
    memo_id = sent_memo(client, brand, creator)

    disputes = read(client, memo_id, creator)["about_brand"]["disputes"]

    assert disputes == {
        "deals_agreed": 2,
        "went_to_dispute": 2,
        "outcomes": NO_DISPUTES | {"unresolved": 1, "resolved_paid": 1},
    }
    assert set(disputes) == {"deals_agreed", "went_to_dispute", "outcomes"}


# --- the two of them ----------------------------------------------------------------


def test_the_first_deal_together_then_not_once_one_finished(
    client, clock, unlimited, brand, creator, other_brand, other_creator
):
    # Each has history with someone else, which never counts between them.
    finish_deal(client, brand, other_creator, accepted_memo(client, brand, other_creator))
    finish_deal(client, other_brand, creator, accepted_memo(client, other_brand, creator))
    first = accepted_memo(client, brand, creator)

    for reader in (brand, creator):
        assert read(client, first, reader)["between_you"] == {
            "first_deal_together": True,
            "earlier_deals_agreed": 0,
            "earlier_deals_finished": 0,
        }

    finish_deal(client, brand, creator, first)
    clock.advance(timedelta(hours=1))
    unfinished = accepted_memo(client, brand, creator)
    clock.advance(timedelta(hours=1))
    second = sent_memo(client, brand, creator)

    for reader in (brand, creator):
        assert read(client, second, reader)["between_you"] == {
            "first_deal_together": False,
            "earlier_deals_agreed": 2,
            "earlier_deals_finished": 1,
        }
    # A deal agreed later is never an earlier one.
    assert read(client, first, creator)["between_you"]["first_deal_together"] is True
    assert read(client, unfinished, brand)["between_you"] == {
        "first_deal_together": False,
        "earlier_deals_agreed": 1,
        "earlier_deals_finished": 1,
    }


# --- a takedown and a block ---------------------------------------------------------------


def test_a_withheld_creator_profile_keeps_its_channels_out(
    client, db, clock, brand, creator, other_creator
):
    admin = User(create_account(db, "admin").id, "admin", clock)
    for each in (creator, other_creator):
        add_channel(db, profile_of(db, each))
        connection(db, profile_of(db, each).id, user=f"'{uuid.uuid4().hex}'")
    memo_id = sent_memo(client, brand, creator)
    other_memo = sent_memo(client, brand, other_creator)
    shown = read(client, memo_id, brand)["about_creator"]
    assert (len(shown["channels"]), len(shown["connected_accounts"])) == (1, 1)

    withheld = withhold(client, admin, "creator", creator_id_of(db, creator))
    assert withheld.status_code == 201, withheld.text

    about = read(client, memo_id, brand)["about_creator"]
    assert about["profile_withheld"] is True
    assert (about["channels"], about["connected_accounts"]) == ([], [])
    kept = read(client, other_memo, brand)["about_creator"]
    assert (len(kept["channels"]), len(kept["connected_accounts"])) == (1, 1)


# --- who may read it ------------------------------------------------------------------


def test_a_stranger_brand_and_a_stranger_creator_get_404(
    client, brand, creator, other_brand, other_creator
):
    memo_id = sent_memo(client, brand, creator)

    for stranger in (other_brand, other_creator):
        response = client.get(check_url(memo_id), headers=stranger.headers)
        assert (response.status_code, response.json()["code"]) == (404, "memo_not_found")


def test_a_memo_that_does_not_exist_is_404(client, brand):
    response = client.get(check_url(str(uuid.uuid4())), headers=brand.headers)

    assert (response.status_code, response.json()["code"]) == (404, "memo_not_found")


def test_it_needs_a_login(client, brand, creator):
    memo_id = sent_memo(client, brand, creator)

    assert client.get(check_url(memo_id)).status_code == 401


def test_an_invalid_id_is_rejected(client, brand):
    assert client.get(check_url("not-an-id"), headers=brand.headers).status_code == 422


def test_it_is_rate_limited(client, brand, creator):
    memo_id = sent_memo(client, brand, creator)
    for _ in range(int(READ_LIMIT.split()[0])):
        assert client.get(check_url(memo_id), headers=creator.headers).status_code == 200

    response = client.get(check_url(memo_id), headers=creator.headers)

    assert response.status_code == 429
    assert "Retry-After" in response.headers


# --- a fixed number of queries ----------------------------------------------------------


@pytest.mark.parametrize("reader", ["brand", "creator"])
def test_a_long_history_costs_the_same_queries_as_a_short_one(
    client, db, clock, unlimited, reader, other_brand, other_creator
):
    """Pairs with one earlier deal and with five, each deal finished,
    disputed or with a channel and connection: the same count. A pair with
    none skips the stage's queries, so it costs fewer, never more."""

    def history(deals: int) -> int:
        brand, creator = brand_user(db, clock), creator_user(db, clock)
        add_channel(db, profile_of(db, creator))
        connection(db, profile_of(db, creator).id, user=f"'{uuid.uuid4().hex}'")
        for n in range(deals):
            memo = accepted_memo(client, brand, creator)
            if n % 2:
                disputed_memo = marked_paid(client, brand, creator)
                client.post(
                    f"{MEMOS_URL}/{disputed_memo}/payment/dispute",
                    json={"reason": REASON},
                    headers=creator.headers,
                )
            finish_deal(client, brand, creator, memo)
            clock.advance(timedelta(minutes=5))
        # Others' deals, so the filters have rows to leave out.
        finish_deal(
            client, brand, other_creator, accepted_memo(client, brand, other_creator)
        )
        finish_deal(
            client, other_brand, creator, accepted_memo(client, other_brand, creator)
        )
        memo_id = sent_memo(client, brand, creator)
        user = brand if reader == "brand" else creator
        return queries_for(client, check_url(memo_id), user.headers)

    none, short, long = history(0), history(1), history(5)

    assert none < short == long, (none, short, long)
