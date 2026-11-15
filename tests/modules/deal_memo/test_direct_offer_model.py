"""The direct_offer table's rules, each broken with raw SQL (D-189).

database.md section 3: every rule the database can hold, it holds, and each
has a test that writes the forbidden row and watches the database refuse it
by name. Each case starts from one valid waiting offer and changes the
columns it names inside a savepoint, so exactly one rule is broken.
"""

import uuid
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from tests.deal_flow import accepted_memo, brand_user, creator_user

HASH = "a" * 64
OTHER_HASH = "b" * 64


def insert(db: Session, creator_id: uuid.UUID, token_hash: str = HASH) -> uuid.UUID:
    """A valid waiting offer, written with raw SQL."""
    return db.execute(
        text(
            "INSERT INTO direct_offer (creator_id, token_hash, recipient_phone_hash,"
            " recipient_phone, brand_name, deliverables, fee_amount_paise,"
            " cancellation_fee_paise, approval_window_days, payment_due_days,"
            " content_due_on, disclosure_required, draft_review, terms_sha256,"
            " expires_at, created_at)"
            " VALUES (:creator, :token, :hash, '+919876543210', 'Amma Sweets',"
            " 'Two reels', 900000, 0, 7, 7, DATE '2026-10-15', true, false, :hash,"
            " now() + interval '14 days', now()) RETURNING id"
        ),
        {"creator": creator_id, "token": token_hash, "hash": HASH},
    ).scalar_one()


@pytest.fixture
def offer(db: Session, clock) -> dict[str, Any]:
    creator = creator_user(db, clock)
    creator_id = db.execute(
        text("SELECT id FROM creator WHERE account_id = :a"), {"a": creator.account_id}
    ).scalar_one()
    return {"id": insert(db, creator_id), "creator_id": creator_id}


def test_a_valid_waiting_offer_is_accepted(db, offer):
    status = db.execute(
        text("SELECT status FROM direct_offer WHERE id = :id"), {"id": offer["id"]}
    ).scalar_one()

    assert status == "sent"


ENDED = (
    "status = 'withdrawn', ended_at = now(), recipient_phone = NULL, brand_name = NULL"
)


@pytest.mark.parametrize(
    ("change", "rule"),
    [
        (
            "status = 'paused', ended_at = now(), recipient_phone = NULL, brand_name = NULL",
            "ck_direct_offer_status_allowed",
        ),
        ("token_hash = 'not-a-hash'", "ck_direct_offer_token_hash_format"),
        ("token_hash = upper(token_hash)", "ck_direct_offer_token_hash_format"),
        ("recipient_phone_hash = 'x'", "ck_direct_offer_recipient_phone_hash_format"),
        ("terms_sha256 = 'x'", "ck_direct_offer_terms_sha256_format"),
        ("recipient_phone = '9876543210'", "ck_direct_offer_recipient_phone_format"),
        ("recipient_phone = '+915876543210'", "ck_direct_offer_recipient_phone_format"),
        ("brand_name = '   '", "ck_direct_offer_brand_name_not_blank"),
        # The number and the name are kept while it waits, and only then.
        ("recipient_phone = NULL", "ck_direct_offer_recipient_kept_only_while_waiting"),
        ("brand_name = NULL", "ck_direct_offer_recipient_kept_only_while_waiting"),
        (
            "status = 'withdrawn', ended_at = now(), brand_name = NULL",
            "ck_direct_offer_recipient_kept_only_while_waiting",
        ),
        (
            "status = 'expired', ended_at = now(), recipient_phone = NULL",
            "ck_direct_offer_recipient_kept_only_while_waiting",
        ),
        ("ended_at = now()", "ck_direct_offer_ended_at_matches_status"),
        (
            "status = 'withdrawn', recipient_phone = NULL, brand_name = NULL",
            "ck_direct_offer_ended_at_matches_status",
        ),
        (
            "status = 'accepted', ended_at = now(), recipient_phone = NULL,"
            " brand_name = NULL",
            "ck_direct_offer_deal_only_when_accepted",
        ),
        ("expires_at = created_at", "ck_direct_offer_lifetime_within_limit"),
        (
            "expires_at = created_at + interval '14 days 1 second'",
            "ck_direct_offer_lifetime_within_limit",
        ),
        (
            "opened_at = created_at - interval '1 second'",
            "ck_direct_offer_opened_after_sent",
        ),
        (
            "status = 'withdrawn', ended_at = created_at - interval '1 second',"
            " recipient_phone = NULL, brand_name = NULL",
            "ck_direct_offer_ended_after_sent",
        ),
        ("deliverables = '   '", "ck_direct_offer_deliverables_length"),
        ("deliverables = repeat('x', 2001)", "ck_direct_offer_deliverables_length"),
        ("deliverable_items = '{}'::jsonb", "ck_direct_offer_deliverable_items_list"),
        (
            "deliverable_items = (SELECT jsonb_agg(n) FROM generate_series(1, 11) n)",
            "ck_direct_offer_deliverable_items_list",
        ),
        ("fee_amount_paise = 0", "ck_direct_offer_fee_positive"),
        ("currency = 'USD'", "ck_direct_offer_currency_allowed"),
        ("cancellation_fee_paise = -1", "ck_direct_offer_cancellation_fee_not_negative"),
        ("approval_window_days = 0", "ck_direct_offer_approval_window_range"),
        ("approval_window_days = 31", "ck_direct_offer_approval_window_range"),
        ("payment_due_days = 0", "ck_direct_offer_payment_due_range"),
        ("payment_due_days = 31", "ck_direct_offer_payment_due_range"),
        ("usage_rights_days = 0", "ck_direct_offer_usage_rights_range"),
        ("usage_rights_days = 3651", "ck_direct_offer_usage_rights_range"),
        ("extra_terms = repeat('x', 2001)", "ck_direct_offer_extra_terms_length"),
    ],
)
def test_the_database_refuses_a_broken_offer(db, offer, change, rule):
    with pytest.raises(IntegrityError, match=rule), db.begin_nested():
        db.execute(
            text(f"UPDATE direct_offer SET {change} WHERE id = :id"),  # noqa: S608 - fixed SQL from the cases above
            {"id": offer["id"]},
        )


def test_an_offer_that_ended_keeps_neither_number_nor_name(db, offer):
    db.execute(
        text(f"UPDATE direct_offer SET {ENDED} WHERE id = :id"),  # noqa: S608 - a fixed change
        {"id": offer["id"]},
    )

    kept = db.execute(
        text("SELECT recipient_phone, brand_name FROM direct_offer WHERE id = :id"),
        {"id": offer["id"]},
    ).one()
    assert tuple(kept) == (None, None)


def test_one_token_opens_one_offer(db, offer):
    with (
        pytest.raises(IntegrityError, match="uq_direct_offer_token_hash"),
        db.begin_nested(),
    ):
        insert(db, offer["creator_id"])


def test_one_deal_comes_from_one_offer(client, db, clock, offer):
    second = insert(db, offer["creator_id"], OTHER_HASH)
    memo = accepted_memo(client, brand_user(db, clock), creator_user(db, clock))
    accepted = (
        "status = 'accepted', ended_at = now(), recipient_phone = NULL,"
        " brand_name = NULL, deal_memo_id = :memo"
    )
    db.execute(
        text(f"UPDATE direct_offer SET {accepted} WHERE id = :id"),  # noqa: S608 - a fixed change
        {"id": offer["id"], "memo": memo},
    )

    with (
        pytest.raises(IntegrityError, match="uq_direct_offer_deal_memo_id"),
        db.begin_nested(),
    ):
        db.execute(
            text(f"UPDATE direct_offer SET {accepted} WHERE id = :id"),  # noqa: S608 - a fixed change
            {"id": second, "memo": memo},
        )
