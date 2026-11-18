"""A direct offer's hidden campaign and application reach nobody (D-189).

Accepting a direct offer makes a campaign of type `direct` and an
application of origin `direct`, so the deal can run on every path a deal
already takes. They are nobody's campaign to find or apply to: each list or
figure below is read with a normal campaign beside the hidden one, in the
same city and niche, and must show the normal one and never the hidden
(testing.md section 2: two of every kind, so an over-broad filter that hid
both, or a missing one that showed both, fails).
"""

import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from sqlalchemy import select

from app.core.clock import india_date
from app.main import app
from app.modules.admin import numbers_service
from app.modules.auth.sender import FakeOtpSender, get_otp_sender
from app.modules.campaigns.alert_models import CampaignAlertSend
from app.modules.campaigns.models import Application, Campaign
from app.modules.deal_memo.models import DealMemo
from app.modules.insights import city_figures_service
from app.modules.matching import embedder
from app.modules.matching import service as matching
from app.modules.matching.models import CampaignEmbedding
from tests.deal_flow import CAMPAIGNS_URL, User, brand_user
from tests.direct_offers import accept, bearer, sent, switch_on
from tests.factories import build_campaign, build_creator, fake_phone
from tests.modules.matching.test_embedding_service import FakeEncoder


@pytest.fixture
def sender(client) -> Iterator[FakeOtpSender]:
    fake = FakeOtpSender()
    app.dependency_overrides[get_otp_sender] = lambda: fake
    yield fake
    app.dependency_overrides.pop(get_otp_sender, None)


def creator_in(db, clock, city: str) -> User:
    creator = build_creator(
        db,
        handle=f"hid{uuid.uuid4().hex[:12]}",
        city=city,
        niches=["food"],
        passport_published_at=clock.now,
    )
    db.add(creator)
    db.flush()
    return User(creator.account_id, "creator", clock)


@pytest.fixture
def world(client, db, clock, sender, monkeypatch) -> dict[str, Any]:
    """In a city of its own: a normal open food campaign with an application
    waiting, and a direct deal agreed by a creator of the same city and niche."""
    switch_on(monkeypatch)
    city = f"Hidden{uuid.uuid4().hex[:8]}"
    brand = brand_user(db, clock)
    normal = client.post(
        CAMPAIGNS_URL,
        json={
            "title": "Pongal sweets launch",
            "description": "Three reels featuring our new sweet box.",
            "campaign_type": "paid",
            "budget_min_paise": 500_000,
            "budget_max_paise": 1_500_000,
            "cities": [city],
            "niches": ["food"],
            "deliverables": "3 Instagram reels",
        },
        headers=brand.headers,
    ).json()["id"]
    published = client.post(f"{CAMPAIGNS_URL}/{normal}/publish", headers=brand.headers)
    assert published.status_code == 200, published.text
    applicant = creator_in(db, clock, city)
    applied = client.post(
        f"{CAMPAIGNS_URL}/{normal}/applications",
        json={"pitch": "I run a street-food page here, with 12,000 followers."},
        headers=applicant.headers,
    )
    assert applied.status_code == 201, applied.text
    reader = creator_in(db, clock, city)

    before = {
        "rates": client.get(
            "/api/v1/rate-guidance",
            params={
                "platform": "instagram",
                "format": "reel",
                "followers": 12_000,
                "niche": "food",
                "city": city,
            },
            headers=reader.headers,
        ).json(),
        "numbers": numbers_service.founder_numbers(
            db, ending_on=india_date(clock.now), days=7, city=city
        ),
    }

    offering = creator_in(db, clock, city)
    phone = fake_phone()
    offer = sent(client, offering, phone)
    accepted = accept(client, sender, offer, phone)
    assert accepted.status_code == 200, accepted.text
    body = accepted.json()
    memo = db.get_one(DealMemo, body["deal_memo_id"])
    application = db.get_one(Application, memo.application_id)
    return {
        "city": city,
        "brand": brand,
        "normal": normal,
        "hidden": str(application.campaign_id),
        "hidden_application": str(application.id),
        "applicant": applicant,
        "reader": reader,
        "offering": offering,
        "direct_brand": bearer(body["access_token"]),
        "before": before,
    }


def ids(items: list[dict[str, Any]], key: str = "id") -> set[str]:
    return {item[key] for item in items}


def test_discovery_shows_the_normal_campaign_only(client, world):
    found = client.get(
        f"{CAMPAIGNS_URL}/discover",
        params={"city": world["city"]},
        headers=world["reader"].headers,
    ).json()["items"]

    assert ids(found) == {world["normal"]}


def test_campaigns_for_me_show_the_normal_campaign_only(client, world):
    found = client.get(
        f"{CAMPAIGNS_URL}/discover/for-me", headers=world["reader"].headers
    ).json()["matches"]

    campaigns = {item["campaign"]["id"] for item in found}
    assert world["normal"] in campaigns
    assert world["hidden"] not in campaigns


def test_no_campaign_route_reads_the_hidden_campaign(client, world):
    def answer(campaign: str, headers: dict[str, str], tail: str = "") -> int:
        return client.get(
            f"{CAMPAIGNS_URL}/{campaign}{tail}", headers=headers
        ).status_code

    # Its own brand, and the creator of its deal, read it as not found.
    assert answer(world["hidden"], world["direct_brand"]) == 404
    assert answer(world["hidden"], world["offering"].headers) == 404
    assert answer(world["hidden"], world["direct_brand"], "/matches") == 404
    assert answer(world["hidden"], world["direct_brand"], "/applications") == 404
    # Beside it, the normal campaign answers its brand.
    assert answer(world["normal"], world["brand"].headers) == 200
    assert answer(world["normal"], world["brand"].headers, "/matches") == 200
    assert answer(world["normal"], world["brand"].headers, "/applications") == 200


def test_the_brand_s_campaigns_and_the_creator_s_applications_leave_it_out(client, world):
    own_campaigns = client.get(CAMPAIGNS_URL, headers=world["direct_brand"]).json()
    normal_campaigns = client.get(CAMPAIGNS_URL, headers=world["brand"].headers).json()
    own_applications = client.get(
        "/api/v1/applications/me", headers=world["offering"].headers
    ).json()
    normal_applications = client.get(
        "/api/v1/applications/me", headers=world["applicant"].headers
    ).json()
    hidden_application = client.get(
        f"/api/v1/applications/{world['hidden_application']}",
        headers=world["offering"].headers,
    )

    assert own_campaigns["items"] == []
    assert ids(normal_campaigns["items"]) == {world["normal"]}
    assert own_applications["items"] == []
    assert len(normal_applications["items"]) == 1
    assert hidden_application.status_code == 404


def test_no_application_route_reaches_the_hidden_application(client, world):
    """Each of the three application checks (the brand's, the creator's own,
    and either party's read) leaves the direct application out, while the
    normal one beside it answers. The hidden one is accepted, so without the
    checks these answer 409 or 200, never 404."""
    hidden = f"/api/v1/applications/{world['hidden_application']}"
    normal_items = client.get(
        f"{CAMPAIGNS_URL}/{world['normal']}/applications",
        headers=world["brand"].headers,
    ).json()["items"]
    (normal_application,) = normal_items
    normal = f"/api/v1/applications/{normal_application['id']}"
    brand, creator = world["direct_brand"], world["offering"].headers

    # The brand's own application routes (get_owned_application).
    for tail in ("/shortlist", "/accept", "/withdraw-invitation"):
        response = client.post(f"{hidden}{tail}", headers=brand)
        assert (tail, response.status_code) == (tail, 404), response.text
        assert response.json()["code"] == "application_not_found"
    # The creator's own (get_own_application).
    for tail in ("/withdraw", "/accept-invitation", "/decline-invitation"):
        response = client.post(f"{hidden}{tail}", headers=creator)
        assert (tail, response.status_code) == (tail, 404), response.text
        assert response.json()["code"] == "application_not_found"
    # Either party's reads (get_visible_application).
    for headers in (brand, creator):
        for tail in ("", "/offers"):
            assert client.get(f"{hidden}{tail}", headers=headers).status_code == 404
    # Beside it, the normal application answers its brand and its creator.
    assert client.get(normal, headers=world["brand"].headers).status_code == 200
    assert client.get(f"{normal}/offers", headers=world["applicant"].headers).status_code == 200
    shortlisted = client.post(f"{normal}/shortlist", headers=world["brand"].headers)
    assert shortlisted.status_code == 200, shortlisted.text


def test_only_the_normal_campaign_is_embedded_for_matching(db, world):
    embedder.set_model(FakeEncoder())
    try:
        result = matching.refresh_campaigns(
            db, campaign_ids=[uuid.UUID(world["normal"]), uuid.UUID(world["hidden"])]
        )
        db.flush()
    finally:
        embedder.set_model(None)

    assert result.embedded == 1
    assert db.get(CampaignEmbedding, uuid.UUID(world["normal"])) is not None
    assert db.get(CampaignEmbedding, uuid.UUID(world["hidden"])) is None


def test_only_the_normal_campaign_is_sent_to_saved_alerts(db, world):
    queued = set(
        db.scalars(
            select(CampaignAlertSend.campaign_id).where(
                CampaignAlertSend.campaign_id.in_(
                    [uuid.UUID(world["normal"]), uuid.UUID(world["hidden"])]
                )
            )
        ).all()
    )

    assert queued == {uuid.UUID(world["normal"])}


def test_the_city_s_open_campaigns_leave_the_hidden_one_out(db, clock, world):
    # Five open campaigns in all, the floor below which the figure is null.
    for _ in range(4):
        db.add(build_campaign(db, cities=[world["city"]], niches=["food"]))
    db.flush()
    hidden = db.get_one(Campaign, uuid.UUID(world["hidden"]))
    assert hidden.cities == [world["city"]]

    figures = city_figures_service.for_city(db, world["city"], india_date(clock.now))

    assert figures.open_campaigns == 5


def test_rate_guidance_is_the_same_after_a_direct_deal(client, world):
    after = client.get(
        "/api/v1/rate-guidance",
        params={
            "platform": "instagram",
            "format": "reel",
            "followers": 12_000,
            "niche": "food",
            "city": world["city"],
        },
        headers=world["reader"].headers,
    ).json()

    assert after == world["before"]["rates"]


def test_the_founders_numbers_count_the_deal_but_no_campaign_or_application(
    db, clock, world
):
    before = world["before"]["numbers"].current
    after = numbers_service.founder_numbers(
        db, ending_on=india_date(clock.now), days=7, city=world["city"]
    ).current

    assert before.campaigns_posted == after.campaigns_posted == 1
    assert before.applications_sent == after.applications_sent == 1
    assert (before.invitations_sent, after.invitations_sent) == (0, 0)
    assert after.deals_agreed == before.deals_agreed + 1


def test_attention_shows_the_normal_campaign_s_applications_only(client, world):
    normal = client.get("/api/v1/me/attention", headers=world["brand"].headers).json()
    direct = client.get("/api/v1/me/attention", headers=world["direct_brand"]).json()
    offering = client.get(
        "/api/v1/me/attention", headers=world["offering"].headers
    ).json()

    reviews = [i for i in normal["items"] if i["kind"] == "review_applications"]
    assert [i["campaign_id"] for i in reviews] == [world["normal"]]
    assert direct["counts"]["review_applications"] == 0
    assert offering["counts"]["answer_invitation"] == 0
    assert world["hidden"] not in {
        item.get("campaign_id")
        for item in direct["items"] + offering["items"]
        if item["kind"] in ("review_applications", "answer_invitation")
    }


def test_no_deal_is_repeated_onto_the_hidden_campaign(client, world):
    """The brand made at the link repeats its deal onto a campaign of its own
    choosing, never onto the hidden one, which reads as not found."""
    memos = client.get(
        "/api/v1/deal-memos/mine", headers=world["offering"].headers
    ).json()["items"]
    (memo,) = memos

    onto_hidden = client.post(
        f"/api/v1/deal-memos/{memo['id']}/repeat",
        json={"campaign_id": world["hidden"]},
        headers=world["direct_brand"],
    )

    assert onto_hidden.status_code == 404
    assert onto_hidden.json()["code"] == "campaign_not_found"
