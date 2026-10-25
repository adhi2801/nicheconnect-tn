"""Counter-offers on a quote (item 44, D-123), through the API.

Both sides counter, at most 3 each; the other side accepts, declines or
answers back; an agreed figure pre-fills the memo and is shown beside a
different fee; the application cannot be accepted while an offer waits.
The pure rules have their property tests (test_offer_properties.py), the
table its rules (test_offer_model.py), the races their own file.
"""

from datetime import timedelta

import pytest
from sqlalchemy import select

from app.modules.auth.models.creator import Creator
from app.modules.campaigns.offer_models import MAX_OFFERS_PER_SIDE
from app.modules.me import export_service
from app.modules.notifications.models import Notification
from tests.deal_flow import (
    CAMPAIGNS_URL,
    MEMOS_URL,
    PITCH,
    User,
    brand_user,
    creator_user,
)
from tests.factories import create_account
from tests.query_counts import queries_for

QUOTE = 600_000


@pytest.fixture
def brand(db, clock) -> User:
    user = brand_user(db, clock)
    db.commit()
    return user


@pytest.fixture
def creator(db, clock) -> User:
    user = creator_user(db, clock)
    db.commit()
    return user


def open_campaign(client, brand: User, campaign_type: str = "paid") -> str:
    body = {
        "title": "Pongal sweets launch",
        "description": "Reels featuring our new sweet box.",
        "campaign_type": campaign_type,
        "cities": ["Madurai"],
        "niches": ["food"],
        "deliverables": "2 Instagram reels",
    }
    if campaign_type == "paid":
        body |= {"budget_min_paise": 300_000, "budget_max_paise": 1_500_000}
    campaign_id = client.post(CAMPAIGNS_URL, json=body, headers=brand.headers).json()[
        "id"
    ]
    published = client.post(
        f"{CAMPAIGNS_URL}/{campaign_id}/publish", headers=brand.headers
    )
    assert published.status_code == 200, published.text
    return str(campaign_id)


def apply(client, brand: User, creator: User, campaign_type: str = "paid") -> str:
    campaign_id = open_campaign(client, brand, campaign_type)
    body: dict = {"pitch": PITCH}
    if campaign_type == "paid":
        body["quoted_amount_paise"] = QUOTE
    response = client.post(
        f"{CAMPAIGNS_URL}/{campaign_id}/applications", json=body, headers=creator.headers
    )
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


def offers_url(application_id: str) -> str:
    return f"/api/v1/applications/{application_id}/offers"


def offer(client, user: User, application_id: str, amount: int, note: str | None = None):
    body: dict = {"amount_paise": amount}
    if note is not None:
        body["note"] = note
    return client.post(offers_url(application_id), json=body, headers=user.headers)


def made(client, user: User, application_id: str, amount: int) -> str:
    response = offer(client, user, application_id, amount)
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


def answer(client, user: User, application_id: str, offer_id: str, move: str):
    return client.post(
        f"{offers_url(application_id)}/{offer_id}/{move}", headers=user.headers
    )


def application(client, user: User, application_id: str) -> dict:
    response = client.get(f"/api/v1/applications/{application_id}", headers=user.headers)
    assert response.status_code == 200, response.text
    return response.json()


def told(db, user: User, kind: str) -> list[dict]:
    return [
        n.details
        for n in db.scalars(
            select(Notification).where(
                Notification.account_id == user.account_id,
                Notification.notification_type == kind,
            )
        )
    ]


# --- making and answering --------------------------------------------------------


def test_a_brand_counters_a_quote_and_the_creator_is_told(client, db, brand, creator):
    application_id = apply(client, brand, creator)

    response = offer(client, brand, application_id, 450_000, "Two reels at this fee?")

    assert response.status_code == 201, response.text
    body = response.json()
    assert (body["side"], body["amount_paise"], body["outcome"]) == (
        "brand",
        450_000,
        None,
    )
    assert body["currency"] == "INR"
    seen = application(client, creator, application_id)
    assert seen["open_offer"]["id"] == body["id"]
    assert seen["agreed_amount_paise"] is None
    [details] = told(db, creator, "offer_received")
    assert details["amount_paise"] == 450_000


def test_accepting_agrees_the_figure_and_tells_the_maker(client, db, brand, creator):
    application_id = apply(client, brand, creator)
    offer_id = made(client, brand, application_id, 450_000)

    response = answer(client, creator, application_id, offer_id, "accept")

    assert response.status_code == 200, response.text
    assert response.json()["outcome"] == "accepted"
    for user in (brand, creator):
        seen = application(client, user, application_id)
        assert seen["agreed_amount_paise"] == 450_000
        assert seen["open_offer"] is None
    assert len(told(db, brand, "offer_accepted")) == 1


def test_a_counter_replaces_the_open_offer(client, brand, creator):
    application_id = apply(client, brand, creator)
    first = made(client, brand, application_id, 400_000)

    second = made(client, creator, application_id, 520_000)

    history = client.get(offers_url(application_id), headers=brand.headers).json()
    assert [(o["id"], o["side"], o["outcome"]) for o in history] == [
        (first, "brand", "replaced"),
        (second, "creator", None),
    ]
    assert history[0]["answered_at"] is not None


def test_declining_leaves_the_application_waiting(client, db, brand, creator):
    application_id = apply(client, brand, creator)
    offer_id = made(client, creator, application_id, 700_000)

    response = answer(client, brand, application_id, offer_id, "decline")

    assert response.json()["outcome"] == "declined"
    seen = application(client, brand, application_id)
    assert (seen["status"], seen["open_offer"]) == ("submitted", None)
    assert len(told(db, creator, "offer_declined")) == 1
    # Either side may still offer.
    assert offer(client, brand, application_id, 650_000).status_code == 201


def test_withdrawing_takes_it_back_and_tells_the_other_side(client, db, brand, creator):
    application_id = apply(client, brand, creator)
    offer_id = made(client, brand, application_id, 400_000)

    response = client.delete(
        f"{offers_url(application_id)}/{offer_id}", headers=brand.headers
    )

    assert response.status_code == 204
    history = client.get(offers_url(application_id), headers=creator.headers).json()
    assert history[0]["outcome"] == "withdrawn"
    assert len(told(db, creator, "offer_withdrawn")) == 1


# --- moves that belong to the other side, or are too late --------------------------


def test_nobody_answers_their_own_offer(client, brand, creator):
    application_id = apply(client, brand, creator)
    offer_id = made(client, brand, application_id, 400_000)

    for move in ("accept", "decline"):
        response = answer(client, brand, application_id, offer_id, move)
        assert response.status_code == 409
        assert response.json()["code"] == "offer_not_yours_to_answer"


def test_nobody_withdraws_the_other_sides_offer(client, brand, creator):
    application_id = apply(client, brand, creator)
    offer_id = made(client, brand, application_id, 400_000)

    response = client.delete(
        f"{offers_url(application_id)}/{offer_id}", headers=creator.headers
    )

    assert response.status_code == 409
    assert response.json()["code"] == "offer_not_yours_to_answer"


def test_an_answered_offer_cannot_be_answered_again(client, brand, creator):
    application_id = apply(client, brand, creator)
    offer_id = made(client, brand, application_id, 400_000)
    assert answer(client, creator, application_id, offer_id, "decline").status_code == 200

    for move in ("accept", "decline"):
        response = answer(client, creator, application_id, offer_id, move)
        assert response.json()["code"] == "offer_already_answered"
    withdrawn = client.delete(
        f"{offers_url(application_id)}/{offer_id}", headers=brand.headers
    )
    assert withdrawn.json()["code"] == "offer_already_answered"


def test_ones_own_open_offer_is_withdrawn_before_another(client, brand, creator):
    application_id = apply(client, brand, creator)
    made(client, brand, application_id, 400_000)

    response = offer(client, brand, application_id, 420_000)

    assert response.status_code == 409
    assert response.json()["code"] == "offer_open"


def test_each_side_makes_at_most_three(client, brand, creator):
    application_id = apply(client, brand, creator)
    for round_ in range(MAX_OFFERS_PER_SIDE):
        made(client, brand, application_id, 400_000 + round_)
        made(client, creator, application_id, 700_000 - round_)

    response = offer(client, brand, application_id, 500_000)

    assert response.status_code == 409
    assert response.json()["code"] == "offer_limit_reached"
    # The creator's last offer still waits for an answer.
    assert application(client, brand, application_id)["open_offer"]["side"] == "creator"


def test_nothing_more_is_offered_once_a_figure_is_agreed(client, brand, creator):
    application_id = apply(client, brand, creator)
    offer_id = made(client, brand, application_id, 400_000)
    answer(client, creator, application_id, offer_id, "accept")

    for user in (brand, creator):
        response = offer(client, user, application_id, 500_000)
        assert response.json()["code"] == "offer_already_agreed"


# --- the application and the offer, together -----------------------------------------


def test_the_application_waits_for_an_open_offer_to_be_settled(client, brand, creator):
    application_id = apply(client, brand, creator)
    client.post(f"/api/v1/applications/{application_id}/shortlist", headers=brand.headers)
    offer_id = made(client, creator, application_id, 700_000)

    refused = client.post(
        f"/api/v1/applications/{application_id}/accept", headers=brand.headers
    )
    answer(client, brand, application_id, offer_id, "accept")
    accepted = client.post(
        f"/api/v1/applications/{application_id}/accept", headers=brand.headers
    )

    assert refused.status_code == 409
    assert refused.json()["code"] == "offer_open"
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["agreed_amount_paise"] == 700_000


@pytest.mark.parametrize(
    ("maker", "outcome"), [("creator", "declined"), ("brand", "withdrawn")]
)
def test_rejecting_the_application_ends_its_open_offer(
    client, brand, creator, maker, outcome
):
    application_id = apply(client, brand, creator)
    made(client, brand if maker == "brand" else creator, application_id, 500_000)

    rejected = client.post(
        f"/api/v1/applications/{application_id}/reject",
        json={"reason": "budget_mismatch"},
        headers=brand.headers,
    )

    assert rejected.status_code == 200, rejected.text
    assert rejected.json()["open_offer"] is None
    history = client.get(offers_url(application_id), headers=creator.headers).json()
    assert history[0]["outcome"] == outcome


def test_an_invitation_can_be_negotiated_before_it_is_answered(
    client, db, brand, creator
):
    campaign_id = open_campaign(client, brand)
    creator_id = db.scalars(
        select(Creator.id).where(Creator.account_id == creator.account_id)
    ).one()
    invitation_id = client.post(
        f"{CAMPAIGNS_URL}/{campaign_id}/invitations",
        json={"creator_id": str(creator_id)},
        headers=brand.headers,
    ).json()["id"]
    offer_id = made(client, creator, invitation_id, 900_000)

    refused = client.post(
        f"/api/v1/applications/{invitation_id}/accept-invitation", headers=creator.headers
    )
    answer(client, brand, invitation_id, offer_id, "accept")
    accepted = client.post(
        f"/api/v1/applications/{invitation_id}/accept-invitation", headers=creator.headers
    )

    assert refused.json()["code"] == "offer_open"
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["agreed_amount_paise"] == 900_000


def test_a_barter_campaign_has_no_figure_to_offer(client, brand, creator):
    application_id = apply(client, brand, creator, "barter")

    response = offer(client, brand, application_id, 100_000)

    assert response.status_code == 409
    assert response.json()["code"] == "offers_closed"


def test_an_accepted_application_is_no_longer_open_to_offers(client, brand, creator):
    application_id = apply(client, brand, creator)
    client.post(f"/api/v1/applications/{application_id}/shortlist", headers=brand.headers)
    client.post(f"/api/v1/applications/{application_id}/accept", headers=brand.headers)

    response = offer(client, creator, application_id, 700_000)

    assert response.json()["code"] == "offers_closed"


def test_a_closed_campaign_takes_no_offers(client, db, brand, creator):
    application_id = apply(client, brand, creator)
    campaign_id = application(client, brand, application_id)["campaign_id"]
    client.post(f"{CAMPAIGNS_URL}/{campaign_id}/close", headers=brand.headers)

    response = offer(client, creator, application_id, 700_000)

    assert response.json()["code"] == "campaign_not_open"


# --- the memo -----------------------------------------------------------------------------


def accepted_with_figure(client, brand: User, creator: User, figure: int) -> str:
    application_id = apply(client, brand, creator)
    client.post(f"/api/v1/applications/{application_id}/shortlist", headers=brand.headers)
    offer_id = made(client, brand, application_id, figure)
    answer(client, creator, application_id, offer_id, "accept")
    accepted = client.post(
        f"/api/v1/applications/{application_id}/accept", headers=brand.headers
    )
    assert accepted.status_code == 200, accepted.text
    return application_id


def test_the_agreed_figure_fills_in_the_memos_fee(client, brand, creator):
    application_id = accepted_with_figure(client, brand, creator, 480_000)

    memo = client.post(
        f"{MEMOS_URL}/for-application/{application_id}",
        json={"deliverables": "2 reels.", "content_due_on": "2026-12-31"},
        headers=brand.headers,
    )

    assert memo.status_code == 201, memo.text
    assert (
        memo.json()["fee_amount_paise"] == memo.json()["agreed_amount_paise"] == 480_000
    )


def test_a_different_fee_is_shown_beside_the_agreed_figure(client, brand, creator):
    application_id = accepted_with_figure(client, brand, creator, 480_000)
    memo_id = client.post(
        f"{MEMOS_URL}/for-application/{application_id}",
        json={"deliverables": "2 reels.", "fee_amount_paise": 400_000},
        headers=brand.headers,
    ).json()["id"]

    for user in (brand, creator):
        read = client.get(f"{MEMOS_URL}/{memo_id}", headers=user.headers)
        if user is creator:
            # A draft is the brand's alone until it is sent.
            assert read.status_code == 404
            continue
        assert (read.json()["fee_amount_paise"], read.json()["agreed_amount_paise"]) == (
            400_000,
            480_000,
        )
    listed = client.get(f"{MEMOS_URL}/mine", headers=brand.headers).json()["items"]
    assert [m["agreed_amount_paise"] for m in listed if m["id"] == memo_id] == [480_000]


def test_a_memo_without_an_offer_says_so(client, brand, creator):
    application_id = apply(client, brand, creator)
    client.post(f"/api/v1/applications/{application_id}/shortlist", headers=brand.headers)
    client.post(f"/api/v1/applications/{application_id}/accept", headers=brand.headers)

    memo = client.post(
        f"{MEMOS_URL}/for-application/{application_id}",
        json={"deliverables": "2 reels.", "fee_amount_paise": 500_000},
        headers=brand.headers,
    )

    assert memo.json()["agreed_amount_paise"] is None


# --- what is shown, to whom ------------------------------------------------------------------


def test_a_brands_note_asking_for_money_is_flagged(client, brand, creator):
    application_id = apply(client, brand, creator)

    response = offer(
        client, brand, application_id, 400_000, "Pay a 2,000 registration fee to confirm."
    )

    assert {flag["field"] for flag in response.json()["text_flags"]} == {"note"}


def test_a_creator_naming_a_price_in_a_note_is_not_flagged(client, brand, creator):
    application_id = apply(client, brand, creator)

    # The same words from a brand are flagged (the test above): a creator
    # asking for their own fee is ordinary, so only contact is checked.
    note = "Pay a 2,000 registration fee to confirm."
    response = offer(client, creator, application_id, 700_000, note)

    assert response.json()["text_flags"] == []


def test_both_exports_hold_the_offers(client, db, brand, creator, clock):
    from app.modules.auth.models.account import Account

    application_id = apply(client, brand, creator)
    made(client, brand, application_id, 400_000)
    made(client, creator, application_id, 650_000)

    for user in (brand, creator):
        exported = export_service.build_export(
            db, db.get_one(Account, user.account_id), clock.now
        )
        rows = exported["data"]["quote_offers"]
        assert [(row["side"], row["amount_paise"]) for row in rows] == [
            ("brand", 400_000),
            ("creator", 650_000),
        ]


def test_a_list_of_applications_costs_the_same_queries_however_many_have_offers(
    client, db, clock, brand
):
    campaign_id = open_campaign(client, brand)
    url = f"{CAMPAIGNS_URL}/{campaign_id}/applications"
    first = creator_user(db, clock)
    db.commit()
    application_id = client.post(
        f"{CAMPAIGNS_URL}/{campaign_id}/applications",
        json={"pitch": PITCH, "quoted_amount_paise": QUOTE},
        headers=first.headers,
    ).json()["id"]
    made(client, brand, application_id, 400_000)
    one = queries_for(client, url, brand.headers)
    for _ in range(4):
        other = creator_user(db, clock)
        db.commit()
        other_id = client.post(
            f"{CAMPAIGNS_URL}/{campaign_id}/applications",
            json={"pitch": PITCH, "quoted_amount_paise": QUOTE},
            headers=other.headers,
        ).json()["id"]
        made(client, brand, other_id, 400_000)

    assert queries_for(client, url, brand.headers) == one


# --- who may -------------------------------------------------------------------------------------


def test_offering_needs_a_login(client, brand, creator):
    application_id = apply(client, brand, creator)

    assert (
        client.post(offers_url(application_id), json={"amount_paise": 1}).status_code
        == 401
    )
    assert client.get(offers_url(application_id)).status_code == 401


@pytest.mark.parametrize(
    "body",
    [
        {"amount_paise": 0},
        {"amount_paise": -5},
        {"amount_paise": 400_000, "note": "x" * 501},
        {"amount_paise": 400_000, "note": ""},
        {"amount_paise": 400_000, "unexpected": True},
        {},
    ],
)
def test_a_bad_offer_is_refused(client, brand, creator, body):
    application_id = apply(client, brand, creator)

    assert (
        client.post(
            offers_url(application_id), json=body, headers=brand.headers
        ).status_code
        == 422
    )


def test_a_stranger_sees_nothing(client, db, clock, brand, creator):
    application_id = apply(client, brand, creator)
    offer_id = made(client, brand, application_id, 400_000)
    strangers = [brand_user(db, clock), creator_user(db, clock)]
    admin = User(create_account(db, "admin").id, "admin", clock)
    db.commit()

    for stranger in [*strangers, admin]:
        assert (
            client.get(offers_url(application_id), headers=stranger.headers).status_code
            == 404
        )
        assert offer(client, stranger, application_id, 1).status_code == 404
        assert (
            answer(client, stranger, application_id, offer_id, "accept").status_code
            == 404
        )


def test_an_offer_on_another_application_is_not_found(client, brand, creator):
    first = apply(client, brand, creator)
    second = apply(client, brand, creator)
    offer_id = made(client, brand, first, 400_000)

    response = answer(client, creator, second, offer_id, "accept")

    assert response.status_code == 404
    assert response.json()["code"] == "offer_not_found"


def test_a_retry_with_the_same_key_makes_one_offer(client, brand, creator):
    application_id = apply(client, brand, creator)
    headers = {**brand.headers, "Idempotency-Key": "offer-retry-1"}

    first = client.post(
        offers_url(application_id), json={"amount_paise": 400_000}, headers=headers
    )
    second = client.post(
        offers_url(application_id), json={"amount_paise": 400_000}, headers=headers
    )

    assert first.status_code == second.status_code == 201
    assert second.json() == first.json()
    assert len(client.get(offers_url(application_id), headers=brand.headers).json()) == 1


def test_a_creator_who_leaves_takes_their_open_offer_with_them(
    client, db, clock, brand, creator
):
    from app.modules.auth.models.account import Account
    from app.modules.me import account_deletion_service

    application_id = apply(client, brand, creator)
    made(client, creator, application_id, 700_000)
    account = db.get_one(Account, creator.account_id)
    account.deletion_requested_at = clock.now - timedelta(days=31)
    account.deletion_takes_effect_at = account.deletion_requested_at + timedelta(days=30)
    db.commit()

    assert account_deletion_service.erase(db, account.id, clock.now) == "erased"

    history = client.get(offers_url(application_id), headers=brand.headers).json()
    assert [o["outcome"] for o in history] == ["withdrawn"]
