"""A draft's approval and the deal's stage, for any history (item 27, D-140).

Tries any draft time, any window, any mix of draft statuses and any later
moment, against what must always hold: approval by the clock never comes
undone with time, an answered draft is never approved by the clock, and a
deal agreed with a draft review never reaches In progress before a draft
is approved, while a deal without one never notices drafts at all.
"""

import uuid
from datetime import UTC, datetime, timedelta

from hypothesis import given
from hypothesis import strategies as st

from app.modules.deal_memo.draft_models import DRAFT_STATUSES, ContentDraft
from app.modules.deal_memo.draft_rules import approved_among, is_approved
from app.modules.deal_memo.models import MAX_WINDOW_DAYS, DealMemo
from app.modules.deal_memo.review_clock import approval_deadline
from app.modules.deal_memo.stage import DRAFT_REVIEW, IN_PROGRESS, stage_of

START = datetime(2026, 9, 1, tzinfo=UTC)
minutes = st.integers(min_value=0, max_value=120 * 24 * 60)
windows = st.integers(min_value=1, max_value=MAX_WINDOW_DAYS)


def memo(window: int, draft_review: bool = True) -> DealMemo:
    return DealMemo(
        id=uuid.uuid4(),
        status="accepted",
        approval_window_days=window,
        payment_due_days=7,
        fee_amount_paise=800_000,
        deliverables="2 reels.",
        draft_review=draft_review,
    )


def draft(at: datetime, status: str = "submitted", round_: int = 1) -> ContentDraft:
    return ContentDraft(
        id=uuid.uuid4(),
        round=round_,
        body="The caption.",
        status=status,
        created_at=at,
        approved_at=at if status == "approved" else None,
    )


histories = st.lists(
    st.tuples(minutes, st.sampled_from(DRAFT_STATUSES)), min_size=0, max_size=4
)


def build(steps) -> list[ContentDraft]:
    return [
        draft(START + timedelta(minutes=at), status, i + 1)
        for i, (at, status) in enumerate(sorted(steps))
    ]


@given(at=minutes, window=windows, later=minutes)
def test_approval_by_the_clock_never_comes_undone(at, window, later):
    d = draft(START + timedelta(minutes=at))
    m = memo(window)
    deadline = approval_deadline(m, d, [d])

    assert is_approved(m, d, [d], deadline)
    assert is_approved(m, d, [d], deadline + timedelta(minutes=later))
    assert not is_approved(m, d, [d], deadline - timedelta(microseconds=1))


@given(at=minutes, window=windows, later=minutes)
def test_an_answered_draft_is_never_approved_by_the_clock(at, window, later):
    d = draft(START + timedelta(minutes=at), "changes_requested")

    assert not is_approved(memo(window), d, [d], START + timedelta(minutes=at + later))


@given(steps=histories, window=windows, now=minutes)
def test_no_work_goes_ahead_before_a_draft_is_approved(steps, window, now):
    m = memo(window)
    drafts = build(steps)
    when = START + timedelta(minutes=now)

    found = stage_of(m, [], None, when, drafts=drafts)

    if approved_among(m, drafts, when) is None:
        assert found.stage != IN_PROGRESS
        assert found.stage == (DRAFT_REVIEW if drafts else "agreed")
    else:
        assert found.stage != DRAFT_REVIEW


@given(steps=histories, window=windows, now=minutes)
def test_a_deal_without_a_draft_review_never_notices_drafts(steps, window, now):
    m = memo(window, draft_review=False)
    when = START + timedelta(minutes=now)

    assert stage_of(m, [], None, when, drafts=build(steps)) == stage_of(m, [], None, when)
