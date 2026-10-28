"""The quote_offer table's rules, each broken with raw SQL (item 44, D-123).

The database holds them, so no bug or hand-written query can make a second
open offer, an answer without its time, or a figure that is not money
(database.md section 3).
"""

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from tests.factories import build_brand, build_campaign, build_creator
from tests.modules.campaigns.test_offer_api import QUOTE


@pytest.fixture
def application_id(db) -> uuid.UUID:
    brand = build_brand(db, email=f"offer-model-{uuid.uuid4().hex[:10]}@example.com")
    creator = build_creator(db, handle=f"om{uuid.uuid4().hex[:12]}")
    db.add_all([brand, creator])
    db.flush()
    campaign = build_campaign(db, status="open", brand_id=brand.id)
    db.add(campaign)
    db.flush()
    return db.execute(
        text(
            "INSERT INTO application (campaign_id, creator_id, pitch, quoted_amount_paise,"
            " status_changed_at) VALUES (:c, :k, 'A Madurai food page, for a model test.',"
            " :q, now()) RETURNING id"
        ),
        {"c": campaign.id, "k": creator.id, "q": QUOTE},
    ).scalar_one()


def insert(db, application_id, **overrides) -> None:
    values = {
        "side": "'brand'",
        "amount_paise": "400000",
        "currency": "'INR'",
        "note": "NULL",
        "made_at": "now()",
        "outcome": "NULL",
        "answered_at": "NULL",
    }
    values.update(overrides)
    db.execute(
        text(
            f"INSERT INTO quote_offer (application_id, {', '.join(values)})"  # noqa: S608 - fixed SQL from the parameters below
            f" VALUES (:a, {', '.join(values.values())})"
        ),
        {"a": application_id},
    )


@pytest.mark.parametrize(
    ("overrides", "rule"),
    [
        ({"side": "'agency'"}, "ck_quote_offer_side_allowed"),
        ({"amount_paise": "0"}, "ck_quote_offer_amount_positive"),
        ({"amount_paise": "-1"}, "ck_quote_offer_amount_positive"),
        ({"currency": "'USD'"}, "ck_quote_offer_currency_allowed"),
        ({"note": "'   '"}, "ck_quote_offer_note_length"),
        ({"note": "repeat('x', 501)"}, "ck_quote_offer_note_length"),
        (
            {"outcome": "'haggled'", "answered_at": "now()"},
            "ck_quote_offer_outcome_allowed",
        ),
        ({"outcome": "'accepted'"}, "ck_quote_offer_answered_with_its_time"),
        ({"answered_at": "now()"}, "ck_quote_offer_answered_with_its_time"),
        (
            {"outcome": "'declined'", "answered_at": "now() - interval '1 hour'"},
            "ck_quote_offer_answered_after_made",
        ),
    ],
)
def test_the_database_refuses_a_bad_offer(db, application_id, overrides, rule):
    with pytest.raises(IntegrityError, match=rule):
        insert(db, application_id, **overrides)


def test_a_second_open_offer_is_refused(db, application_id):
    insert(db, application_id)

    with pytest.raises(IntegrityError, match="uq_quote_offer_one_open"):
        insert(db, application_id, side="'creator'")


def test_answered_offers_may_be_many(db, application_id):
    for side in ("'brand'", "'creator'", "'brand'"):
        insert(db, application_id, side=side, outcome="'replaced'", answered_at="now()")
    insert(db, application_id)


def test_an_application_with_offers_cannot_be_deleted(db, application_id):
    insert(db, application_id)

    with pytest.raises(IntegrityError, match="fk_quote_offer_application_id_application"):
        db.execute(text("DELETE FROM application WHERE id = :a"), {"a": application_id})
