"""Suggesting campaigns to a creator, and saying why, including how the brand pays.

The mirror of test_matching_api.py. Every test works in a city of its own, so
a laptop's seeded campaigns (most of them open, in Madurai) can never land
in the results.
"""

import uuid
from collections.abc import Iterator
from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event

import app.db.models
from app.core.rate_limit import limiter
from app.db.session import get_db
from app.main import app
from app.modules.auth.dependencies import get_now
from app.modules.auth.tokens import create_access_token
from app.modules.campaigns.models import Application
from app.modules.deal_memo.models import DealMemo
from app.modules.matching import embedder, service
from app.modules.payment_status import service as payments
from tests.factories import (
    FIXED_NOW,
    build_brand,
    build_campaign,
    build_creator,
    create_account,
)
from tests.modules.auth.test_suspension_api import suspend

URL = "/api/v1/campaigns/discover/for-me"
PUBLISHED_AT = datetime(2026, 9, 1, 9, 0, tzinfo=FIXED_NOW.tzinfo)
PITCH = "I film food reels in this city every week and would love to do this one."


class KeywordEncoder:
    """Biryani texts point one way, everything else the other.

    Enough to prove the ranking follows the vectors without loading a model.
    """

    def encode(self, sentences, **kwargs):
        size = embedder.EXPECTED_DIMENSIONS
        return [
            [1.0, 0.0] + [0.0] * (size - 2)
            if "biryani" in text.lower()
            else [0.0, 1.0] + [0.0] * (size - 2)
            for text in sentences
        ]


@pytest.fixture
def encoder() -> Iterator[KeywordEncoder]:
    fake = KeywordEncoder()
    embedder.set_model(fake)
    try:
        yield fake
    finally:
        embedder.set_model(None)


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


@pytest.fixture
def city() -> str:
    """A city no seeded row uses, so only this test's campaigns can match."""
    return f"Testur {uuid.uuid4().hex[:8]}"


def a_brand(db):
    brand = build_brand(db, email=f"cm-{uuid.uuid4().hex[:12]}@example.com")
    db.add(brand)
    db.flush()
    return brand


def a_campaign(db, brand, city, **overrides):
    fields = {
        "brand_id": brand.id,
        "status": "open",
        "cities": [city],
        "niches": ["food"],
    }
    fields.update(overrides)
    campaign = build_campaign(db, **fields)
    db.add(campaign)
    db.flush()
    return campaign


def a_creator(db, city, *, published=False, niches=("food",), bio=None):
    creator = build_creator(
        db,
        handle=f"cm{uuid.uuid4().hex[:12]}",
        city=city,
        niches=list(niches),
        bio=bio,
        passport_published_at=PUBLISHED_AT if published else None,
    )
    db.add(creator)
    db.flush()
    return creator


def login(creator) -> dict[str, str]:
    token, _ = create_access_token(creator.account_id, "creator", FIXED_NOW)
    return {"Authorization": f"Bearer {token}"}


def apply(db, campaign, creator, status="submitted") -> Application:
    application = Application(
        campaign_id=campaign.id,
        creator_id=creator.id,
        pitch=PITCH,
        status=status,
        # The table requires a reason on every rejection.
        rejection_reason="timing" if status == "rejected" else None,
        status_changed_at=FIXED_NOW,
        created_at=FIXED_NOW,
        updated_at=FIXED_NOW,
    )
    db.add(application)
    db.flush()
    return application


def an_overdue_payment(db, brand, city):
    """A payment this brand owes on another deal, due 8 September and unpaid."""
    elsewhere = a_campaign(db, brand, f"{city} east")
    worker = a_creator(db, f"{city} east")
    memo = DealMemo(
        application_id=apply(db, elsewhere, worker, status="accepted").id,
        deliverables="3 Instagram reels.",
        fee_amount_paise=800_000,
        created_at=FIXED_NOW,
        updated_at=FIXED_NOW,
    )
    db.add(memo)
    db.flush()
    return payments.create_for_memo(db, memo, approved_on=date(2026, 9, 1), now=FIXED_NOW)


def titles(response) -> list[str]:
    return [row["campaign"]["title"] for row in response.json()["matches"]]


# --- the happy path ------------------------------------------------------------


def test_a_creator_sees_an_open_campaign_in_their_city_and_niche(client, db, city):
    campaign = a_campaign(db, a_brand(db), city, niches=["food", "travel"])
    creator = a_creator(db, city, niches=("food", "fashion"))

    response = client.get(URL, headers=login(creator))

    assert response.status_code == 200
    body = response.json()
    assert [row["campaign"]["id"] for row in body["matches"]] == [str(campaign.id)]
    reasons = body["matches"][0]["reasons"]
    assert reasons["shared_niches"] == ["food"]
    assert reasons["city"] == city


def test_without_embeddings_the_list_is_newest_first_and_says_so(client, db, city):
    brand = a_brand(db)
    a_campaign(db, brand, city, title="Older", created_at=FIXED_NOW - timedelta(days=2))
    a_campaign(db, brand, city, title="Newer", created_at=FIXED_NOW - timedelta(days=1))
    creator = a_creator(db, city)

    response = client.get(URL, headers=login(creator))

    assert titles(response) == ["Newer", "Older"]
    assert response.json()["ranked_by_similarity"] is False
    assert all(row["reasons"]["similarity"] is None for row in response.json()["matches"])


def test_with_embeddings_the_closest_brief_comes_first(client, db, city, encoder):
    brand = a_brand(db)
    # The saree campaign is newer, so only the vectors can put biryani first.
    biryani = a_campaign(
        db, brand, city, title="Biryani week", created_at=FIXED_NOW - timedelta(days=3)
    )
    saree = a_campaign(
        db, brand, city, title="Saree sale", created_at=FIXED_NOW - timedelta(days=1)
    )
    creator = a_creator(db, city, published=True, bio="Biryani reels from my street.")
    service.refresh_creators(db, creator_ids=[creator.id])
    service.refresh_campaigns(db, campaign_ids=[biryani.id, saree.id])

    response = client.get(URL, headers=login(creator))

    assert titles(response) == ["Biryani week", "Saree sale"]
    body = response.json()
    assert body["ranked_by_similarity"] is True
    assert body["matches"][0]["reasons"]["similarity"] == pytest.approx(1.0)
    assert body["matches"][1]["reasons"]["similarity"] == pytest.approx(0.0)


def test_a_campaign_not_yet_embedded_sorts_last_rather_than_vanishing(
    client, db, city, encoder
):
    brand = a_brand(db)
    indexed = a_campaign(db, brand, city, title="Saree sale")
    a_campaign(db, brand, city, title="Not indexed yet", created_at=FIXED_NOW)
    creator = a_creator(db, city, published=True, bio="Sarees and street food.")
    service.refresh_creators(db, creator_ids=[creator.id])
    service.refresh_campaigns(db, campaign_ids=[indexed.id])

    response = client.get(URL, headers=login(creator))

    assert titles(response) == ["Saree sale", "Not indexed yet"]
    assert response.json()["matches"][1]["reasons"]["similarity"] is None


def test_the_limit_is_honoured(client, db, city):
    brand = a_brand(db)
    for n in range(3):
        a_campaign(db, brand, city, title=f"Campaign {n}")
    creator = a_creator(db, city)

    response = client.get(URL, params={"limit": 2}, headers=login(creator))

    assert len(response.json()["matches"]) == 2


# --- who is kept out -------------------------------------------------------------


def test_a_campaign_in_another_city_is_not_suggested(client, db, city):
    a_campaign(db, a_brand(db), f"{city} north")
    creator = a_creator(db, city)

    assert client.get(URL, headers=login(creator)).json()["matches"] == []


def test_a_campaign_sharing_no_niche_is_not_suggested(client, db, city):
    a_campaign(db, a_brand(db), city, niches=["tech"])
    creator = a_creator(db, city, niches=("food",))

    assert client.get(URL, headers=login(creator)).json()["matches"] == []


def test_a_campaign_that_is_not_open_is_not_suggested(client, db, city):
    a_campaign(db, a_brand(db), city, status="draft")
    creator = a_creator(db, city)

    assert client.get(URL, headers=login(creator)).json()["matches"] == []


def test_applications_closed_yesterday_are_not_suggested_but_closing_today_is(
    client, db, city
):
    brand = a_brand(db)
    today = FIXED_NOW.date()
    a_campaign(
        db, brand, city, title="Closed", applications_close_on=today - timedelta(days=1)
    )
    a_campaign(db, brand, city, title="Last day", applications_close_on=today)
    creator = a_creator(db, city)

    assert titles(client.get(URL, headers=login(creator))) == ["Last day"]


def test_a_suspended_brands_campaign_is_not_suggested(client, db, city):
    brand = a_brand(db)
    a_campaign(db, brand, city)
    suspend(db, brand.account_id)
    creator = a_creator(db, city)

    assert client.get(URL, headers=login(creator)).json()["matches"] == []


@pytest.mark.parametrize("status", ["submitted", "withdrawn", "rejected"])
def test_a_campaign_already_applied_to_is_not_suggested_again(client, db, city, status):
    campaign = a_campaign(db, a_brand(db), city)
    creator = a_creator(db, city)
    apply(db, campaign, creator, status=status)

    assert client.get(URL, headers=login(creator)).json()["matches"] == []


def test_another_creators_application_does_not_hide_the_campaign(client, db, city):
    campaign = a_campaign(db, a_brand(db), city)
    apply(db, campaign, a_creator(db, city))
    creator = a_creator(db, city)

    assert len(client.get(URL, headers=login(creator)).json()["matches"]) == 1


# --- the brand's payment record ------------------------------------------------


def test_each_suggestion_carries_the_brands_payment_record(client, db, city):
    brand = a_brand(db)
    a_campaign(db, brand, city)
    an_overdue_payment(db, brand, city)
    creator = a_creator(db, city)

    record = client.get(URL, headers=login(creator)).json()["matches"][0]["reasons"][
        "brand_payments"
    ]

    assert record["brand_id"] == str(brand.id)
    assert record["currently_overdue"] == 1
    # Below three completed deals the figures are withheld, never zero.
    assert record["status"] == "new_brand_no_history_yet"
    assert record["paid_on_time_share"] is None


def test_the_record_is_exactly_what_the_brands_own_page_says(client, db, city):
    brand = a_brand(db)
    a_campaign(db, brand, city)
    an_overdue_payment(db, brand, city)
    creator = a_creator(db, city)
    headers = login(creator)

    suggested = client.get(URL, headers=headers).json()["matches"][0]["reasons"]
    own_page = client.get(f"/api/v1/brands/{brand.id}/reliability", headers=headers)

    assert suggested["brand_payments"] == own_page.json()


def test_the_query_count_does_not_grow_with_the_number_of_brands(client, db, city):
    """Two brands or six, the same number of queries: no N+1 (backend.md)."""
    creator = a_creator(db, city)
    headers = login(creator)

    def queries_for(brands: int) -> int:
        for _ in range(brands):
            a_campaign(db, a_brand(db), city)
        statements: list[str] = []

        def count(conn, cursor, statement, *args):
            statements.append(statement)

        engine = db.get_bind().engine
        event.listen(engine, "before_cursor_execute", count)
        try:
            assert client.get(URL, headers=headers).status_code == 200
        finally:
            event.remove(engine, "before_cursor_execute", count)
        return len(statements)

    assert queries_for(2) == queries_for(4)


# --- who may ask ------------------------------------------------------------------


def test_without_a_token_the_answer_is_401(client):
    assert client.get(URL).status_code == 401


def test_a_brand_cannot_ask_for_campaign_suggestions(client, db):
    brand = a_brand(db)
    token, _ = create_access_token(brand.account_id, "brand", FIXED_NOW)

    response = client.get(URL, headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 403


def test_a_creator_with_no_profile_yet_gets_409(client, db):
    account = create_account(db, "creator")
    token, _ = create_access_token(account.id, "creator", FIXED_NOW)

    response = client.get(URL, headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 409


@pytest.mark.parametrize("limit", [0, 51, "many"])
def test_a_bad_limit_is_refused(client, db, city, limit):
    creator = a_creator(db, city)

    response = client.get(URL, params={"limit": limit}, headers=login(creator))

    assert response.status_code == 422


def test_the_path_is_not_swallowed_by_the_campaign_id_route(client, db, city):
    """`/campaigns/{campaign_id}` is registered first. A one-segment path here
    would be read as a bad id and refused with 422; two segments are not."""
    creator = a_creator(db, city)

    assert client.get(URL, headers=login(creator)).status_code == 200
