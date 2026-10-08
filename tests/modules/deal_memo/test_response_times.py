"""Typical response times: the measuring rules, without a database (D-077)."""

import uuid
from datetime import UTC, datetime, timedelta

from app.modules.deal_memo.record_models import DealRecordEntry
from app.modules.deal_memo.response_times import (
    MEMO_ANSWERED,
    MIN_EXAMPLES,
    WORK_REVIEWED,
    summarise,
    waits,
)

START = datetime(2026, 10, 1, 9, 0, tzinfo=UTC)
DEAL_A, DEAL_B = uuid.uuid4(), uuid.uuid4()


def entry(deal: uuid.UUID, kind: str, hours: float) -> DealRecordEntry:
    return DealRecordEntry(
        deal_memo_id=deal, kind=kind, occurred_at=START + timedelta(hours=hours)
    )


def test_each_request_is_timed_to_its_answer():
    entries = [
        entry(DEAL_A, "proof_submitted", 0),
        entry(DEAL_A, "proof_approved", 30),
        entry(DEAL_B, "proof_submitted", 2),
        entry(DEAL_B, "proof_revision_requested", 8),
    ]

    assert waits(entries, *WORK_REVIEWED) == [30, 6]


def test_an_approval_by_the_clock_counts_as_the_wait_it_was():
    entries = [
        entry(DEAL_A, "proof_submitted", 0),
        entry(DEAL_A, "proof_auto_approved", 7 * 24),
    ]

    assert waits(entries, *WORK_REVIEWED) == [168]


def test_a_resubmission_is_timed_again():
    entries = [
        entry(DEAL_A, "proof_submitted", 0),
        entry(DEAL_A, "proof_revision_requested", 10),
        entry(DEAL_A, "proof_submitted", 20),
        entry(DEAL_A, "proof_approved", 24),
    ]

    assert waits(entries, *WORK_REVIEWED) == [10, 4]


def test_a_request_still_waiting_is_not_counted():
    assert waits([entry(DEAL_A, "proof_submitted", 0)], *WORK_REVIEWED) == []


def test_a_memo_withdrawn_before_an_answer_is_left_out():
    entries = [
        entry(DEAL_A, "memo_sent", 0),
        entry(DEAL_A, "memo_cancelled", 5),
        entry(DEAL_B, "memo_sent", 0),
        entry(DEAL_B, "memo_change_requested", 12),
    ]

    assert waits(entries, *MEMO_ANSWERED) == [12]


def test_an_answer_with_no_request_before_it_is_ignored():
    assert waits([entry(DEAL_A, "proof_approved", 3)], *WORK_REVIEWED) == []


def test_other_deals_entries_never_end_a_wait():
    entries = [
        entry(DEAL_A, "proof_submitted", 0),
        entry(DEAL_B, "proof_approved", 1),
    ]

    assert waits(entries, *WORK_REVIEWED) == []


def test_below_five_examples_there_is_not_enough_to_say():
    found = summarise([1.0] * (MIN_EXAMPLES - 1))

    assert (found.examples, found.median_hours) == (4, None)


def test_from_five_examples_the_median_is_given():
    found = summarise([1.0, 2.0, 30.0, 4.0, 5.0])

    assert (found.examples, found.median_hours) == (5, 4.0)


def test_the_median_is_rounded_to_a_tenth_of_an_hour():
    assert summarise([1.04, 1.04, 1.04, 2.0, 2.0]).median_hours == 1.0
