"""The campaign alert tables' rules, each broken with raw SQL (item 43, D-130)."""

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from tests.factories import build_campaign, build_creator


@pytest.fixture
def ids(db) -> dict[str, uuid.UUID]:
    creator = build_creator(db, handle=f"a{uuid.uuid4().hex[:12]}")
    campaign = build_campaign(db)
    db.add_all([creator, campaign])
    db.flush()
    return {"creator": creator.id, "campaign": campaign.id}


def alert(db, creator_id, terms: str) -> None:
    db.execute(
        text(
            f"INSERT INTO campaign_alert (creator_id, city, niche, campaign_type, min_budget_paise) VALUES (:c, {terms})"  # noqa: S608 - fixed SQL from the parameters below
        ),
        {"c": creator_id},
    )


@pytest.mark.parametrize(
    ("terms", "rule"),
    [
        ("NULL, NULL, NULL, NULL", "ck_campaign_alert_names_a_term"),
        ("' M ', NULL, NULL, NULL", "ck_campaign_alert_city_length"),
        ("NULL, 'astrology', NULL, NULL", "ck_campaign_alert_niche_allowed"),
        ("NULL, NULL, 'lottery', NULL", "ck_campaign_alert_type_allowed"),
        ("NULL, NULL, NULL, 0", "ck_campaign_alert_budget_positive"),
        ("NULL, NULL, 'barter', 100", "ck_campaign_alert_no_budget_on_barter"),
    ],
)
def test_the_database_refuses_a_bad_alert(db, ids, terms, rule):
    with pytest.raises(IntegrityError, match=rule):
        alert(db, ids["creator"], terms)


def test_the_database_refuses_another_currency(db, ids):
    with pytest.raises(IntegrityError, match="ck_campaign_alert_currency_allowed"):
        db.execute(
            text(
                "INSERT INTO campaign_alert (creator_id, niche, currency) VALUES (:c, 'food', 'USD')"
            ),
            {"c": ids["creator"]},
        )


@pytest.mark.parametrize(
    ("first", "second"),
    [
        ("'Madurai', NULL, NULL, NULL", "'MADURAI', NULL, NULL, NULL"),  # any case
        ("NULL, 'food', NULL, NULL", "NULL, 'food', NULL, NULL"),  # NULLs equal
    ],
)
def test_the_same_terms_are_held_once_per_creator(db, ids, first, second):
    alert(db, ids["creator"], first)

    with pytest.raises(IntegrityError, match="uq_campaign_alert_terms"):
        alert(db, ids["creator"], second)


def send(db, campaign_id, sent: str, recipients: str) -> None:
    db.execute(
        text(
            f"INSERT INTO campaign_alert_send (campaign_id, queued_at, sent_at, recipients) VALUES (:c, now(), {sent}, {recipients})"  # noqa: S608 - fixed SQL from the parameters below
        ),
        {"c": campaign_id},
    )


@pytest.mark.parametrize(
    ("sent", "recipients", "rule"),
    [
        ("now()", "NULL", "ck_campaign_alert_send_sent_with_recipients"),
        ("NULL", "3", "ck_campaign_alert_send_sent_with_recipients"),
        ("now()", "-1", "ck_campaign_alert_send_recipients_counted"),
    ],
)
def test_the_database_refuses_a_bad_send(db, ids, sent, recipients, rule):
    with pytest.raises(IntegrityError, match=rule):
        send(db, ids["campaign"], sent, recipients)


def test_a_campaign_is_sent_once(db, ids):
    send(db, ids["campaign"], "NULL", "NULL")

    with pytest.raises(IntegrityError, match="uq_campaign_alert_send_campaign_id"):
        send(db, ids["campaign"], "NULL", "NULL")
