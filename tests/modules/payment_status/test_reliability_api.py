"""Reading a brand's payment record over HTTP, end to end through real deals."""

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.modules.auth.models.brand import Brand
from tests.deal_flow import (
    LINK,
    MEMOS_URL,
    accepted_memo,
    brand_user,
    creator_user,
)

RRN = "412345678901"


def reliability_url(brand_id) -> str:
    return f"/api/v1/brands/{brand_id}/reliability"


def brand_id_of(db, user) -> str:
    return str(db.scalar(select(Brand.id).where(Brand.account_id == user.account_id)))


def approved_deal(client: TestClient, db, clock, brand) -> str:
    """One deal taken all the way to approved work, so payment is open."""
    creator = creator_user(db, clock)
    memo_id = accepted_memo(client, brand, creator)
    proof_id = client.post(
        f"{MEMOS_URL}/{memo_id}/proof",
        json={"content_url": LINK, "format": "reel", "disclosure_confirmed": True},
        headers=creator.headers,
    ).json()["id"]
    approved = client.post(
        f"{MEMOS_URL}/{memo_id}/proof/{proof_id}/approve", headers=brand.headers
    )
    assert approved.status_code == 200, approved.text
    return memo_id


def pay(client, brand, memo_id) -> None:
    response = client.post(
        f"{MEMOS_URL}/{memo_id}/payment/mark-paid",
        json={"method": "upi", "reference": RRN},
        headers=brand.headers,
    )
    assert response.status_code == 200, response.text


@pytest.fixture
def brand(client, db, clock):
    return brand_user(db, clock)


# --- the floor ------------------------------------------------------------


def test_a_brand_with_no_deals_reads_as_new(client, db, brand):
    response = client.get(reliability_url(brand_id_of(db, brand)), headers=brand.headers)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "new_brand_no_history_yet"
    assert body["deals_completed"] == 0
    assert body["paid_on_time_share"] is None


def test_figures_stay_hidden_until_three_deals(client, db, brand, clock):
    for _ in range(2):
        pay(client, brand, approved_deal(client, db, clock, brand))

    body = client.get(
        reliability_url(brand_id_of(db, brand)), headers=brand.headers
    ).json()

    assert body["deals_completed"] == 2
    assert body["status"] == "new_brand_no_history_yet"
    assert body["paid_on_time_share"] is None


def test_three_deals_paid_on_time_reads_as_a_clean_record(client, db, brand, clock):
    for _ in range(3):
        pay(client, brand, approved_deal(client, db, clock, brand))

    body = client.get(
        reliability_url(brand_id_of(db, brand)), headers=brand.headers
    ).json()

    assert body["status"] == "has_payment_history"
    assert body["deals_completed"] == 3
    assert body["deals_paid"] == 3
    assert body["paid_on_time_share"] == 1.0
    assert body["median_days_to_pay"] == 0


# --- a brand that does not pay --------------------------------------------


def test_a_brand_that_never_pays_is_shown_as_such(client, db, brand, clock):
    """Nobody has to complain. The calendar reports it."""
    for _ in range(3):
        approved_deal(client, db, clock, brand)
    clock.advance(timedelta(days=40))

    body = client.get(
        reliability_url(brand_id_of(db, brand)), headers=brand.headers
    ).json()

    assert body["status"] == "has_payment_history"
    assert body["deals_unpaid"] == 3
    assert body["paid_on_time_share"] == 0.0
    assert body["median_days_to_pay"] is None


def test_a_new_brand_cannot_hide_a_creator_it_is_still_owing(
    client, db, brand, clock
):
    """The whole point of reporting overdue below the floor."""
    approved_deal(client, db, clock, brand)
    clock.advance(timedelta(days=10))

    body = client.get(
        reliability_url(brand_id_of(db, brand)), headers=brand.headers
    ).json()

    assert body["status"] == "new_brand_no_history_yet"
    assert body["currently_overdue"] == 1


def test_paying_late_shows_in_the_share(client, db, brand, clock):
    on_time = [approved_deal(client, db, clock, brand) for _ in range(2)]
    slow = approved_deal(client, db, clock, brand)
    for memo_id in on_time:
        pay(client, brand, memo_id)
    clock.advance(timedelta(days=10))
    pay(client, brand, slow)

    body = client.get(
        reliability_url(brand_id_of(db, brand)), headers=brand.headers
    ).json()

    assert body["deals_completed"] == 3
    assert body["paid_on_time_share"] == pytest.approx(2 / 3)


# --- who may read it ------------------------------------------------------


def test_a_creator_can_check_a_brand_before_applying(client, db, brand, clock):
    """The only moment this can change a decision."""
    creator = creator_user(db, clock)
    for _ in range(3):
        pay(client, brand, approved_deal(client, db, clock, brand))

    response = client.get(
        reliability_url(brand_id_of(db, brand)), headers=creator.headers
    )

    assert response.status_code == 200
    assert response.json()["paid_on_time_share"] == 1.0


def test_it_is_not_public(client, db, brand):
    """Publishing a business's payment failures to the open internet is a
    different question, and cannot be undone."""
    response = client.get(reliability_url(brand_id_of(db, brand)))

    assert response.status_code == 401


def test_an_unknown_brand_is_not_found(client, brand):
    import uuid

    response = client.get(reliability_url(uuid.uuid4()), headers=brand.headers)

    assert response.status_code == 404


# --- one brand's record is its own ----------------------------------------


def test_one_brands_deals_never_land_on_another_brands_record(
    client, db, brand, clock
):
    other = brand_user(db, clock)
    for _ in range(3):
        pay(client, brand, approved_deal(client, db, clock, brand))

    body = client.get(
        reliability_url(brand_id_of(db, other)), headers=other.headers
    ).json()

    assert body["deals_completed"] == 0
    assert body["status"] == "new_brand_no_history_yet"
