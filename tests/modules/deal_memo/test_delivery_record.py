"""A creator's delivery record: what it says, and what it refuses to hide.

A brand reads this before trusting someone with a launch. Like the brand
payment record it mirrors (D-034), most of these tests are about the ways a
record like this misleads people if it is built carelessly (D-038).
"""

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest

from app.modules.deal_memo import delivery_record
from app.modules.deal_memo.delivery_record import Outcome, classify
from app.modules.deal_memo.models import DealMemo
from app.modules.deal_memo.proof_models import DeliverableProof

CREATOR = uuid.uuid4()
ACCEPTED = datetime(2026, 9, 1, 9, 0, tzinfo=UTC)
DUE_ON = date(2026, 9, 10)
NOW = datetime(2026, 9, 30, 9, 0, tzinfo=UTC)  # 20 days after DUE_ON
LINK = "https://www.instagram.com/reel/abc123/"


def memo(**overrides) -> DealMemo:
    """One accepted memo. Unsaved: the calculation is pure."""
    fields = {
        "id": uuid.uuid4(),
        "status": "accepted",
        "content_due_on": DUE_ON,
        "disclosure_required": True,
        "approval_window_days": 7,
        "accepted_at": ACCEPTED,
        "created_at": ACCEPTED,
        "updated_at": ACCEPTED,
    }
    fields.update(overrides)
    return DealMemo(**fields)


def proof(
    deal: DealMemo, *, day: int, status: str = "approved", **overrides
) -> DeliverableProof:
    """A submission on that day of September, 10:00 UTC (15:30 in India)."""
    submitted = datetime(2026, 9, day, 10, 0, tzinfo=UTC)
    fields = {
        "id": uuid.uuid4(),
        "deal_memo_id": deal.id,
        "content_url": LINK,
        "format": "reel",
        "status": status,
        "disclosure_confirmed": True,
        "created_at": submitted,
        "updated_at": submitted,
    }
    if status == "approved":
        fields["approved_at"] = submitted + timedelta(days=1)
    fields.update(overrides)
    return DeliverableProof(**fields)


def delivered(day: int = 5, campaign_type: str = "paid", **memo_fields):
    """A deal the creator delivered on that day of September."""
    deal = memo(**memo_fields)
    return deal, campaign_type, [proof(deal, day=day)]


def silent(campaign_type: str = "paid", **memo_fields):
    """Accepted, then nothing at all: 20 days past the agreed date."""
    return memo(**memo_fields), campaign_type, []


def build(*deals, now: datetime = NOW):
    return delivery_record.build_record(
        [(deal, campaign_type) for deal, campaign_type, _ in deals],
        {deal.id: proofs for deal, _, proofs in deals},
        CREATOR,
        now,
    )


# --- the floor ------------------------------------------------------------


def test_a_creator_with_no_deals_has_nothing_to_report():
    record = build()

    assert record.status == delivery_record.NO_HISTORY_YET
    assert record.deals_completed == 0
    assert record.currently_overdue == 0
    assert record.delivered_on_time_share is None
    assert record.disclosure_confirmed_share is None


def test_figures_are_withheld_below_three_completed_deals():
    record = build(delivered(), delivered())

    assert record.status == delivery_record.NO_HISTORY_YET
    assert record.deals_completed == 2
    assert record.deals_delivered == 2
    assert record.delivered_on_time_share is None


def test_withheld_is_not_the_same_as_zero():
    # Two perfect deliveries must not read as "0% on time".
    record = build(delivered(), delivered())

    assert record.delivered_on_time_share is None
    assert record.delivered_on_time_share != 0


def test_three_on_time_deliveries_is_a_clean_record():
    record = build(delivered(), delivered(), delivered())

    assert record.status == delivery_record.HAS_HISTORY
    assert record.delivered_on_time_share == 1.0
    assert record.disclosure_confirmed_share == 1.0
    assert record.deals_not_delivered == 0


# --- silence --------------------------------------------------------------


def test_never_delivering_counts_without_anybody_complaining():
    record = build(delivered(), delivered(), silent())

    assert record.deals_completed == 3
    assert record.deals_not_delivered == 1
    assert record.delivered_on_time_share == pytest.approx(2 / 3)


def test_delivering_none_reads_as_zero_not_as_no_figure():
    record = build(silent(), silent(), silent())

    assert record.status == delivery_record.HAS_HISTORY
    assert record.delivered_on_time_share == 0.0


def test_a_few_days_late_is_overdue_not_yet_a_failure():
    # Four days past the date is not the same as never delivering.
    record = build(silent(), now=datetime(2026, 9, 14, 9, 0, tzinfo=UTC))

    assert record.currently_overdue == 1
    assert record.deals_not_delivered == 0
    assert record.deals_completed == 0


def test_the_fourteenth_day_after_the_date_is_when_silence_counts():
    thirteen = datetime(2026, 9, 23, 9, 0, tzinfo=UTC)
    fourteen = datetime(2026, 9, 24, 9, 0, tzinfo=UTC)
    deal = memo()

    assert classify(deal, [], thirteen) is Outcome.OVERDUE
    assert classify(deal, [], fourteen) is Outcome.NOT_DELIVERED


def test_a_new_creator_cannot_hide_work_a_brand_is_still_waiting_for():
    record = build(silent())

    assert record.status == delivery_record.NO_HISTORY_YET
    assert record.currently_overdue == 1


def test_asked_for_changes_and_never_resubmitted_is_not_delivered():
    deal = memo()
    asked = proof(
        deal, day=8, status="revision_requested", revision_note="Fix the caption"
    )

    assert classify(deal, [asked], NOW) is Outcome.NOT_DELIVERED


def test_work_waiting_for_the_brand_is_never_the_creators_lateness():
    deal = memo(approval_window_days=30)
    waiting = proof(deal, day=9, status="submitted")

    assert classify(deal, [waiting], NOW) is Outcome.IN_PROGRESS


def test_work_the_brand_never_reviewed_counts_as_delivered_by_the_clock():
    # The approval window has passed but nobody has read the proof since, so
    # the row still says submitted. The record must not wait for someone to look.
    deal = memo()
    unreviewed = proof(deal, day=9, status="submitted")

    assert classify(deal, [unreviewed], NOW) is Outcome.DELIVERED


def test_a_deal_with_no_agreed_date_is_never_late_or_overdue():
    deal = memo(content_due_on=None)

    assert classify(deal, [], NOW + timedelta(days=365)) is Outcome.IN_PROGRESS
    record = build((deal, "paid", [proof(deal, day=29)]), delivered(), delivered())
    assert record.delivered_on_time_share == 1.0


# --- only what the creator did -------------------------------------------


def test_walking_away_after_starting_counts_against_the_creator():
    walked = memo(status="cancelled", cancellation_kind="cancelled_by_creator")

    record = build(delivered(), delivered(), (walked, "paid", []))

    assert record.deals_not_delivered == 1
    assert record.deals_completed == 3
    # Cancelled work is not owed any more, so it is not overdue.
    assert record.currently_overdue == 0


@pytest.mark.parametrize("kind", ["withdrawn_early", "cancelled_by_brand"])
def test_cancellations_that_were_not_the_creators_doing_are_not_counted(kind):
    cancelled = memo(status="cancelled", cancellation_kind=kind)

    record = build((cancelled, "paid", []))

    assert record.deals_completed == 0
    assert record.deals_not_delivered == 0
    assert record.currently_overdue == 0


def test_the_brand_asking_for_changes_is_not_held_against_the_creator():
    deal = memo()
    first = proof(deal, day=5, status="revision_requested", revision_note="Brighter")
    second = proof(deal, day=7)

    record = build((deal, "paid", [first, second]), delivered(), delivered())

    assert record.deals_delivered == 3
    assert record.delivered_on_time_share == 1.0


# --- on time, on Tamil Nadu's calendar -------------------------------------


def test_on_time_is_judged_by_the_first_submission_not_the_brands_review():
    deal = memo()
    # Submitted on the due date; the brand took a week to approve.
    on_the_day = proof(deal, day=10, approved_at=datetime(2026, 9, 17, 9, 0, tzinfo=UTC))

    record = build((deal, "paid", [on_the_day]), delivered(), delivered())

    assert record.delivered_on_time_share == 1.0


def test_late_evening_utc_on_the_due_date_is_already_late_in_india():
    deal = memo()
    # 20:00 UTC on the 10th is 01:30 on the 11th in Tamil Nadu.
    just_late = proof(deal, day=10, created_at=datetime(2026, 9, 10, 20, 0, tzinfo=UTC))

    record = build((deal, "paid", [just_late]), delivered(), delivered())

    assert record.delivered_on_time_share == pytest.approx(2 / 3)


# --- disclosure -----------------------------------------------------------


def test_disclosure_share_counts_only_deals_that_required_one():
    unconfirmed = memo()
    not_required = memo(disclosure_required=False)

    record = build(
        (unconfirmed, "paid", [proof(unconfirmed, day=5, disclosure_confirmed=False)]),
        (not_required, "paid", [proof(not_required, day=5, disclosure_confirmed=False)]),
        delivered(),
    )

    assert record.disclosure_confirmed_share == pytest.approx(1 / 2)


def test_no_deal_requiring_disclosure_means_no_figure_not_zero():
    record = build(*(delivered(disclosure_required=False) for _ in range(3)))

    assert record.disclosure_confirmed_share is None


# --- barter ---------------------------------------------------------------


def test_barter_is_shown_and_never_scored():
    walked = memo(status="cancelled", cancellation_kind="cancelled_by_creator")

    record = build(
        delivered(campaign_type="barter"),
        (walked, "barter", []),
        silent(campaign_type="barter"),
    )

    assert record.barter_deals_delivered == 1
    assert record.barter_deals_not_delivered == 2
    assert record.deals_completed == 0
    assert record.currently_overdue == 0
    assert record.status == delivery_record.NO_HISTORY_YET


def test_late_barter_work_is_not_reported_as_overdue():
    # Barter is never scored (D-026), and "currently overdue" is a score in
    # all but name. It shows up only once it settles, in the barter counts.
    record = build(
        silent(campaign_type="barter"), now=datetime(2026, 9, 14, 9, 0, tzinfo=UTC)
    )

    assert record.currently_overdue == 0
    assert record.barter_deals_delivered == 0
    assert record.barter_deals_not_delivered == 0
