"""Warnings on free text, as the API answers them (item 60).

Each response that carries free text one person wrote for another carries
`text_flags`, worked out on read. These check the right fields, for the right
reader, at the right moment of a deal.
"""

from sqlalchemy import select

from app.modules.auth.models.creator import Creator
from tests.deal_flow import (
    CAMPAIGNS_URL,
    LINK,
    MEMOS_URL,
    PITCH,
    accepted_memo,
    brand_user,
    creator_user,
)
from tests.modules.campaigns.test_invitation_api import open_campaign

SCAM = "Pay a registration fee of ₹2,000 to confirm your slot."


def flags(body: dict) -> list[tuple[str, str]]:
    return [(f["field"], f["flag"]) for f in body["text_flags"]]


def test_a_brief_asking_creators_for_money_is_flagged_for_everyone(client, db, clock):
    brand, creator = brand_user(db, clock), creator_user(db, clock)
    campaign_id = open_campaign(client, brand, description=SCAM)

    as_brand = client.get(f"{CAMPAIGNS_URL}/{campaign_id}", headers=brand.headers).json()
    as_creator = client.get(
        f"{CAMPAIGNS_URL}/{campaign_id}", headers=creator.headers
    ).json()

    assert flags(as_brand) == flags(as_creator) == [("description", "asks_for_money")]


def test_an_ordinary_brief_has_no_flags(client, db, clock):
    brand = brand_user(db, clock)
    campaign_id = open_campaign(
        client, brand, description="We pay ₹5,000 per reel after approval."
    )

    body = client.get(f"{CAMPAIGNS_URL}/{campaign_id}", headers=brand.headers).json()

    assert body["text_flags"] == []


def test_a_pitch_with_a_phone_number_is_flagged_but_not_a_price(client, db, clock):
    brand, creator = brand_user(db, clock), creator_user(db, clock)
    campaign_id = open_campaign(client, brand)

    body = client.post(
        f"{CAMPAIGNS_URL}/{campaign_id}/applications",
        json={
            "pitch": "My rate is ₹5,000 per reel. Call me on 98765 43210.",
            "quoted_amount_paise": 500_000,
        },
        headers=creator.headers,
    ).json()

    assert flags(body) == [("pitch", "phone_number")]


def test_contact_details_stop_being_a_warning_once_the_deal_is_agreed(client, db, clock):
    brand, creator = brand_user(db, clock), creator_user(db, clock)
    campaign_id = open_campaign(client, brand)
    application = client.post(
        f"{CAMPAIGNS_URL}/{campaign_id}/applications",
        json={"pitch": PITCH + " WhatsApp me for samples."},
        headers=creator.headers,
    ).json()
    assert flags(application) == [("pitch", "messaging_link")]

    client.post(
        f"/api/v1/applications/{application['id']}/shortlist", headers=brand.headers
    )
    accepted = client.post(
        f"/api/v1/applications/{application['id']}/accept", headers=brand.headers
    ).json()

    assert accepted["text_flags"] == []


def test_an_invitation_note_asking_for_money_is_flagged(client, db, clock):
    brand, creator = brand_user(db, clock), creator_user(db, clock)
    campaign_id = open_campaign(client, brand)
    creator_id = db.scalar(
        select(Creator.id).where(Creator.account_id == creator.account_id)
    )

    body = client.post(
        f"{CAMPAIGNS_URL}/{campaign_id}/invitations",
        json={
            "creator_id": str(creator_id),
            "note": "Courier charges of ₹750 to be paid first.",
        },
        headers=brand.headers,
    ).json()

    assert ("invitation_note", "asks_for_money") in flags(body)


def test_memo_terms_asking_for_a_deposit_are_flagged(client, db, clock):
    brand, creator = brand_user(db, clock), creator_user(db, clock)
    memo_id = accepted_memo(
        client,
        brand,
        creator,
        extra_terms="A refundable security deposit of Rs 1500 applies.",
    )

    body = client.get(f"{MEMOS_URL}/{memo_id}", headers=creator.headers).json()

    assert flags(body) == [("extra_terms", "asks_for_money")]


def test_a_revision_note_asking_for_money_is_flagged(client, db, clock):
    brand, creator = brand_user(db, clock), creator_user(db, clock)
    memo_id = accepted_memo(client, brand, creator)
    proof_id = client.post(
        f"{MEMOS_URL}/{memo_id}/proof",
        json={"content_url": LINK, "format": "reel", "disclosure_confirmed": True},
        headers=creator.headers,
    ).json()["id"]

    body = client.post(
        f"{MEMOS_URL}/{memo_id}/proof/{proof_id}/request-revision",
        json={"note": "Pay the processing fee of ₹499 and we approve."},
        headers=brand.headers,
    ).json()

    assert flags(body) == [("revision_note", "asks_for_money")]
