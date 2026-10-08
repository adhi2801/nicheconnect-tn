"""Suspension takes effect at once and everywhere, and never costs the other party
their deal (D-061)."""

import pytest
from sqlalchemy import delete, select, update

from app.main import app
from app.modules.auth.models.account import Account
from app.modules.auth.models.auth_session import AuthSession
from app.modules.auth.models.brand import Brand
from app.modules.auth.models.creator import Creator
from app.modules.auth.sender import FakeOtpSender, get_otp_sender
from app.modules.campaigns.models import Campaign
from app.modules.matching import service as matching
from tests.deal_flow import (
    LINK,
    MEMOS_URL,
    User,
    accepted_memo,
    brand_user,
    creator_user,
)
from tests.factories import FIXED_NOW, build_campaign, build_creator


def suspend(db, account_id, reason: str = "fake_profile") -> None:
    db.execute(
        update(Account)
        .where(Account.id == account_id)
        .values(suspended_at=FIXED_NOW, suspension_reason=reason)
    )
    db.flush()


def restore(db, account_id) -> None:
    db.execute(
        update(Account)
        .where(Account.id == account_id)
        .values(suspended_at=None, suspension_reason=None)
    )
    db.flush()


def profile(db, user: User) -> Creator:
    return db.scalar(select(Creator).where(Creator.account_id == user.account_id))


@pytest.fixture(autouse=True)
def only_this_tests_creators(db) -> None:
    """Search and matching read every published creator; the seeded sample
    data is hidden inside this test's rolled-back transaction."""
    db.execute(update(Creator).values(passport_published_at=None))


@pytest.fixture
def brand(db, clock) -> User:
    return brand_user(db, clock)


@pytest.fixture
def creator(db, clock) -> User:
    user = creator_user(db, clock)
    row = profile(db, user)
    row.passport_published_at = FIXED_NOW
    db.flush()
    return user


# --- the account itself --------------------------------------------------------------


def test_a_suspended_account_is_refused_on_its_next_request(client, db, creator):
    assert client.get("/api/v1/auth/me", headers=creator.headers).status_code == 200
    suspend(db, creator.account_id, "fake_profile")

    response = client.get("/api/v1/auth/me", headers=creator.headers)

    assert response.status_code == 403
    assert response.json()["code"] == "account_suspended"
    assert response.json()["detail"] == "Reason: fake profile."


def test_a_suspended_account_cannot_log_in_and_its_code_stays_unused(client, db, creator):
    sender = FakeOtpSender()
    app.dependency_overrides[get_otp_sender] = lambda: sender
    phone = db.get(Account, creator.account_id).phone
    suspend(db, creator.account_id, "abuse")
    client.post("/api/v1/auth/otp/request", json={"phone": phone})

    response = client.post(
        "/api/v1/auth/otp/verify",
        json={"phone": phone, "code": sender.last_code_for(phone), "role": "creator"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Reason: abuse."


def test_a_suspended_account_cannot_renew_its_session(client, db, clock):
    sender = FakeOtpSender()
    app.dependency_overrides[get_otp_sender] = lambda: sender
    phone = "+919000044401"
    client.post("/api/v1/auth/otp/request", json={"phone": phone})
    login = client.post(
        "/api/v1/auth/otp/verify",
        json={"phone": phone, "code": sender.last_code_for(phone), "role": "creator"},
    ).json()
    account_id = login["account"]["id"]
    suspend(db, account_id)

    response = client.post(
        "/api/v1/auth/refresh", json={"refresh_token": login["refresh_token"]}
    )

    assert response.status_code == 403
    sessions = db.scalars(select(AuthSession).where(AuthSession.account_id == account_id))
    assert all(s.revoked_at is not None for s in sessions)


def test_restoring_brings_the_account_back(client, db, creator):
    suspend(db, creator.account_id)
    restore(db, creator.account_id)

    assert client.get("/api/v1/auth/me", headers=creator.headers).status_code == 200


# --- a suspended creator disappears ---------------------------------------------------


def test_a_suspended_creator_leaves_search(client, db, brand, creator):
    handle = profile(db, creator).handle
    before = client.get("/api/v1/creators", headers=brand.headers).json()["items"]
    suspend(db, creator.account_id)
    after = client.get("/api/v1/creators", headers=brand.headers).json()["items"]

    assert handle in [i["handle"] for i in before]
    assert handle not in [i["handle"] for i in after]


def test_a_suspended_creators_public_page_looks_like_it_never_existed(
    client, db, creator
):
    handle = profile(db, creator).handle
    suspend(db, creator.account_id)

    suspended = client.get(f"/api/v1/creators/by-handle/{handle}")
    missing = client.get("/api/v1/creators/by-handle/nobody.here")

    assert suspended.status_code == missing.status_code == 404
    assert suspended.json()["code"] == missing.json()["code"]


def test_a_suspended_creator_is_never_suggested(db, brand, creator):
    row = profile(db, creator)
    brand_row = db.scalar(select(Brand).where(Brand.account_id == brand.account_id))
    campaign = build_campaign(
        db, brand_id=brand_row.id, status="open", cities=[row.city], niches=row.niches
    )
    db.add(campaign)
    db.flush()
    before = [
        m.creator.id
        for m in matching.find_creators_for_campaign(
            db, campaign, limit=10, today=FIXED_NOW.date()
        )
    ]
    suspend(db, creator.account_id)
    after = [
        m.creator.id
        for m in matching.find_creators_for_campaign(
            db, campaign, limit=10, today=FIXED_NOW.date()
        )
    ]

    assert row.id in before
    assert row.id not in after


# --- a suspended brand's campaigns disappear -------------------------------------------


def open_campaign(db, brand: User) -> Campaign:
    brand_row = db.scalar(select(Brand).where(Brand.account_id == brand.account_id))
    campaign = build_campaign(db, brand_id=brand_row.id, status="open")
    db.add(campaign)
    db.flush()
    return campaign


def test_a_suspended_brands_campaigns_leave_discovery(client, db, brand, creator):
    campaign = open_campaign(db, brand)
    suspend(db, brand.account_id, "non_payment")

    found = []
    cursor = None
    while True:
        params = {"limit": 100, **({"cursor": cursor} if cursor else {})}
        page = client.get(
            "/api/v1/campaigns/discover", params=params, headers=creator.headers
        ).json()
        found += [c["id"] for c in page["items"]]
        cursor = page["next_cursor"]
        if not cursor:
            break

    assert str(campaign.id) not in found


def test_a_suspended_brands_campaign_cannot_be_applied_to_by_its_id(
    client, db, brand, creator
):
    campaign = open_campaign(db, brand)
    suspend(db, brand.account_id, "non_payment")

    response = client.post(
        f"/api/v1/campaigns/{campaign.id}/applications",
        json={"pitch": "I run a Madurai street-food page with 12,000 local followers."},
        headers=creator.headers,
    )

    assert response.status_code == 409
    assert response.json()["code"] == "campaign_not_open"


# --- the other party keeps their deal ---------------------------------------------------


def test_suspending_a_brand_never_costs_the_creator_their_deal(
    client, db, brand, creator
):
    """The creator can still read it, confirm payment and open a dispute."""
    memo_id = accepted_memo(client, brand, creator)
    proof = client.post(
        f"{MEMOS_URL}/{memo_id}/proof",
        json={"content_url": LINK, "format": "reel", "disclosure_confirmed": True},
        headers=creator.headers,
    ).json()["id"]
    client.post(f"{MEMOS_URL}/{memo_id}/proof/{proof}/approve", headers=brand.headers)
    client.post(
        f"{MEMOS_URL}/{memo_id}/payment/mark-paid",
        json={"method": "upi", "reference": "412345678901"},
        headers=brand.headers,
    )

    suspend(db, brand.account_id, "non_payment")

    assert (
        client.get(f"{MEMOS_URL}/{memo_id}", headers=creator.headers).status_code == 200
    )
    dispute = client.post(
        f"{MEMOS_URL}/{memo_id}/payment/dispute",
        json={"reason": "The reference given does not match anything in my account."},
        headers=creator.headers,
    )
    assert dispute.status_code == 201, dispute.text
    record = client.get(f"{MEMOS_URL}/{memo_id}/record", headers=creator.headers)
    assert record.status_code == 200
    assert record.json()["intact"] is True
    # The suspended brand itself can do nothing.
    assert client.get(f"{MEMOS_URL}/{memo_id}", headers=brand.headers).status_code == 403


def test_the_creator_can_still_confirm_payment_from_a_suspended_brand(
    client, db, brand, creator
):
    memo_id = accepted_memo(client, brand, creator)
    proof = client.post(
        f"{MEMOS_URL}/{memo_id}/proof",
        json={"content_url": LINK, "format": "reel", "disclosure_confirmed": True},
        headers=creator.headers,
    ).json()["id"]
    client.post(f"{MEMOS_URL}/{memo_id}/proof/{proof}/approve", headers=brand.headers)
    client.post(
        f"{MEMOS_URL}/{memo_id}/payment/mark-paid",
        json={"method": "upi", "reference": "412345678901"},
        headers=brand.headers,
    )
    suspend(db, brand.account_id, "spam")

    response = client.post(
        f"{MEMOS_URL}/{memo_id}/payment/confirm", headers=creator.headers
    )

    assert response.status_code == 200, response.text


def test_a_suspended_creators_prices_stop_counting_toward_fair_rates(
    client, db, brand, clock
):
    from app.core.taxonomy import CURRENCY
    from app.modules.auth.models.rate_card import CreatorChannel, CreatorPackage

    db.execute(delete(CreatorPackage))
    creators = []
    for price in (100_000, 200_000, 300_000, 400_000, 500_000):
        row = build_creator(
            db,
            handle=f"fair{price}",
            passport_published_at=FIXED_NOW,
            rate_card_public_at=FIXED_NOW,
        )
        db.add(row)
        db.flush()
        db.add(
            CreatorChannel(
                creator_id=row.id,
                platform="instagram",
                profile_url=f"https://instagram.com/fair{price}",
                followers=20_000,
                figures_as_of=FIXED_NOW.date(),
            )
        )
        db.add(
            CreatorPackage(
                creator_id=row.id,
                platform="instagram",
                format="reel",
                title="Reel",
                price_paise=price,
                currency=CURRENCY,
                delivery_days=5,
                position=0,
            )
        )
        creators.append(row)
    db.flush()
    params = {"platform": "instagram", "format": "reel", "followers": 20_000}
    before = client.get(
        "/api/v1/rate-guidance", params=params, headers=brand.headers
    ).json()

    suspend(db, creators[0].account_id)
    after = client.get(
        "/api/v1/rate-guidance", params=params, headers=brand.headers
    ).json()

    assert before["creators_counted"] == 5
    assert after["creators_counted"] == 4
    assert after["median_paise"] is None  # below five: not enough to say
