"""The deal memo table: one per application, with the agreed terms recorded."""

import uuid
from datetime import date, timedelta

import pytest
from sqlalchemy.exc import IntegrityError

from app.modules.campaigns.models import Application
from app.modules.deal_memo.models import DealMemo
from tests.factories import FIXED_NOW, build_campaign, build_creator

PITCH = "I run a Madurai street-food page with 12,000 local followers."


def make_application(db, **overrides) -> Application:
    campaign = build_campaign(db, status="open")
    db.add(campaign)
    creator = build_creator(db, handle=f"memo{uuid.uuid4().hex[:12]}")
    db.add(creator)
    db.flush()
    fields = {
        "campaign_id": campaign.id,
        "creator_id": creator.id,
        "pitch": PITCH,
        "status": "accepted",
        "status_changed_at": FIXED_NOW,
        "created_at": FIXED_NOW,
        "updated_at": FIXED_NOW,
    }
    fields.update(overrides)
    application = Application(**fields)
    db.add(application)
    db.flush()
    return application


def build_memo(db, **overrides) -> DealMemo:
    fields = {
        "deliverables": "3 Instagram reels, 1 story set.",
        "fee_amount_paise": 800_000,
        "created_at": FIXED_NOW,
        "updated_at": FIXED_NOW,
    }
    fields.update(overrides)
    fields.setdefault("application_id", make_application(db).id)
    return DealMemo(**fields)


def assert_rejected_by(db, memo: DealMemo, constraint_name: str) -> None:
    db.add(memo)
    with pytest.raises(IntegrityError) as exc_info:
        db.flush()
    assert constraint_name in str(exc_info.value)


def test_a_memo_starts_as_a_draft_with_the_agreed_defaults(db):
    memo = build_memo(db)
    db.add(memo)
    db.flush()
    db.refresh(memo)

    assert memo.status == "draft"
    assert memo.currency == "INR"
    assert memo.approval_window_days == 7  # D-025
    assert memo.payment_due_days == 7  # D-027
    assert memo.cancellation_fee_paise == 0  # D-026
    assert memo.revision_count == 0
    assert memo.disclosure_required is True
    assert memo.work_started_at is None
    assert memo.cancellation_kind is None


def test_one_memo_per_application(db):
    application = make_application(db)
    db.add(build_memo(db, application_id=application.id))
    db.flush()

    assert_rejected_by(
        db, build_memo(db, application_id=application.id), "uq_deal_memo_application_id"
    )


def test_a_memo_needs_a_real_application(db):
    assert_rejected_by(
        db,
        build_memo(db, application_id=uuid.uuid4()),
        "fk_deal_memo_application_id_application",
    )


def test_an_application_with_a_memo_cannot_be_deleted(db):
    memo = build_memo(db)
    db.add(memo)
    db.flush()
    application = db.get(Application, memo.application_id)

    db.delete(application)
    with pytest.raises(IntegrityError) as exc_info:
        db.flush()
    assert "fk_deal_memo_application_id_application" in str(exc_info.value)


# --- money -----------------------------------------------------------------


def test_a_barter_memo_carries_no_fee(db):
    db.add(build_memo(db, fee_amount_paise=None))
    db.flush()


@pytest.mark.parametrize("fee", [0, -100])
def test_a_fee_must_be_real_money(db, fee):
    assert_rejected_by(
        db, build_memo(db, fee_amount_paise=fee), "ck_deal_memo_fee_positive"
    )


def test_a_cancellation_fee_can_be_agreed_and_defaults_to_zero(db):
    memo = build_memo(db, cancellation_fee_paise=250_000)
    db.add(memo)
    db.flush()

    assert memo.cancellation_fee_paise == 250_000


def test_a_negative_cancellation_fee_is_rejected(db):
    assert_rejected_by(
        db,
        build_memo(db, cancellation_fee_paise=-1),
        "ck_deal_memo_cancellation_fee_not_negative",
    )


def test_only_rupees_for_now(db):
    assert_rejected_by(
        db, build_memo(db, currency="USD"), "ck_deal_memo_currency_allowed"
    )


# --- agreed windows --------------------------------------------------------


@pytest.mark.parametrize("field", ["approval_window_days", "payment_due_days"])
@pytest.mark.parametrize("value", [0, 31])
def test_windows_outside_one_to_thirty_days_are_rejected(db, field, value):
    constraint = (
        "ck_deal_memo_approval_window_range"
        if field == "approval_window_days"
        else "ck_deal_memo_payment_due_range"
    )
    assert_rejected_by(db, build_memo(db, **{field: value}), constraint)


def test_windows_are_stored_per_memo_so_policy_changes_do_not_rewrite_history(db):
    memo = build_memo(db, approval_window_days=14, payment_due_days=3)
    db.add(memo)
    db.flush()
    db.refresh(memo)

    assert (memo.approval_window_days, memo.payment_due_days) == (14, 3)


@pytest.mark.parametrize("days", [0, 3651])
def test_usage_rights_outside_the_allowed_range_are_rejected(db, days):
    assert_rejected_by(
        db, build_memo(db, usage_rights_days=days), "ck_deal_memo_usage_rights_range"
    )


def test_usage_rights_and_a_content_date_can_be_agreed(db):
    memo = build_memo(db, usage_rights_days=180, content_due_on=date(2026, 10, 15))
    db.add(memo)
    db.flush()

    assert memo.usage_rights_days == 180
    assert memo.content_due_on == date(2026, 10, 15)


# --- status and cancellation ----------------------------------------------


@pytest.mark.parametrize(
    "status", ["draft", "sent", "change_requested", "accepted", "declined"]
)
def test_every_allowed_status_is_accepted(db, status):
    db.add(build_memo(db, status=status))
    db.flush()


@pytest.mark.parametrize("status", ["signed", "Draft", ""])
def test_unknown_status_is_rejected(db, status):
    assert_rejected_by(db, build_memo(db, status=status), "ck_deal_memo_status_allowed")


@pytest.mark.parametrize(
    "kind", ["withdrawn_early", "cancelled_by_brand", "cancelled_by_creator"]
)
def test_a_cancelled_memo_records_how_it_ended(db, kind):
    memo = build_memo(
        db, status="cancelled", cancellation_kind=kind, cancelled_at=FIXED_NOW
    )
    db.add(memo)
    db.flush()

    assert memo.cancellation_kind == kind


def test_a_cancellation_without_a_kind_is_rejected(db):
    assert_rejected_by(
        db,
        build_memo(db, status="cancelled"),
        "ck_deal_memo_cancellation_kind_matches_status",
    )


def test_a_kind_without_a_cancellation_is_rejected(db):
    assert_rejected_by(
        db,
        build_memo(db, status="accepted", cancellation_kind="withdrawn_early"),
        "ck_deal_memo_cancellation_kind_matches_status",
    )


def test_an_unknown_cancellation_kind_is_rejected(db):
    assert_rejected_by(
        db,
        build_memo(db, status="cancelled", cancellation_kind="changed_their_mind"),
        "ck_deal_memo_cancellation_kind_allowed",
    )


def test_work_started_marks_the_line_between_cancellations(db):
    """Before work, a cancellation costs nothing; after it, it counts (D-026)."""
    memo = build_memo(db, status="accepted", accepted_at=FIXED_NOW)
    db.add(memo)
    db.flush()
    assert memo.work_started_at is None

    memo.work_started_at = FIXED_NOW + timedelta(days=1)
    db.flush()
    db.refresh(memo)

    assert memo.work_started_at == FIXED_NOW + timedelta(days=1)


def test_revision_count_cannot_go_negative(db):
    assert_rejected_by(
        db, build_memo(db, revision_count=-1), "ck_deal_memo_revision_count_not_negative"
    )


# --- text ------------------------------------------------------------------


@pytest.mark.parametrize("deliverables", ["", "   ", "d" * 2001])
def test_deliverables_must_be_present_and_reasonable(db, deliverables):
    assert_rejected_by(
        db, build_memo(db, deliverables=deliverables), "ck_deal_memo_deliverables_length"
    )


def test_extra_terms_are_optional_but_bounded(db):
    db.add(build_memo(db, extra_terms=None))
    db.flush()

    assert_rejected_by(
        db, build_memo(db, extra_terms="t" * 2001), "ck_deal_memo_extra_terms_length"
    )
