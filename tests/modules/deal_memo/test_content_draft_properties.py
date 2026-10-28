"""A draft's approval and the deal's stage, for any history (item 27, D-140).

Tries any draft time, any window, any mix of draft statuses and any later
moment, against what must always hold: approval by the clock never comes
undone with time, an answered draft is never approved by the clock, and a
deal agreed with a draft review never reaches In progress before a draft
is approved, while a deal without one never notices drafts at all.
"""

import uuid
from datetime import UTC, date, datetime, timedelta

from hypothesis import given
from hypothesis import strategies as st

from app.core.clock import india_date
from app.modules.deal_memo.draft_models import DRAFT_STATUSES, ContentDraft
from app.modules.deal_memo.draft_rules import (
    MIN_ANSWER_DAYS,
    answer_deadline,
    answered_at,
    approved_among,
    days_held_late,
    days_waiting_on_brand,
    delivery_due_on,
    is_approved,
    shown_in_time,
)
from app.modules.deal_memo.models import MAX_WINDOW_DAYS, DealMemo
from app.modules.deal_memo.review_clock import approval_deadline
from app.modules.deal_memo.stage import DRAFT_REVIEW, IN_PROGRESS, stage_of

START = datetime(2026, 9, 1, tzinfo=UTC)
minutes = st.integers(min_value=0, max_value=120 * 24 * 60)
windows = st.integers(min_value=1, max_value=MAX_WINDOW_DAYS)


def memo(window: int, draft_review: bool = True) -> DealMemo:
    return DealMemo(
        content_due_on=date(2026, 12, 31),
        id=uuid.uuid4(),
        status="accepted",
        approval_window_days=window,
        payment_due_days=7,
        fee_amount_paise=800_000,
        deliverables="2 reels.",
        draft_review=draft_review,
    )


def draft(at: datetime, status: str = "submitted", round_: int = 1) -> ContentDraft:
    """A row the database would accept: an answered draft carries its answer's moment."""
    answered = status != "submitted"
    return ContentDraft(
        id=uuid.uuid4(),
        round=round_,
        body="The caption.",
        status=status,
        created_at=at,
        approved_at=at if status == "approved" else None,
        answered_at=at + timedelta(hours=3) if answered else None,
        changes_note="Add the ad label." if status == "changes_requested" else None,
        auto_approved=False,
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
    deadline = answer_deadline(m, d, [d])

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

    with_drafts = stage_of(m, [], None, when, drafts=build(steps))
    without = stage_of(m, [], None, when)

    assert with_drafts == without
    assert with_drafts.work_due_on == without.work_due_on == m.content_due_on


@given(at=minutes, window=windows)
def test_every_draft_gets_its_window_and_at_least_two_whole_days(at, window):
    d = draft(START + timedelta(minutes=at))
    m = memo(window)

    deadline = answer_deadline(m, d, [d])

    assert deadline >= approval_deadline(m, d, [d])
    assert deadline - d.created_at >= timedelta(days=MIN_ANSWER_DAYS)


waits = st.integers(min_value=0, max_value=30 * 24 * 60)


@given(at=minutes, wait=waits, window=windows, due_in=st.integers(0, 60))
def test_a_draft_shown_in_time_never_leaves_the_creator_late(at, wait, window, due_in):
    """Shown on or before the due date: the creator always has the whole day after the answer."""
    m = memo(window)
    d = draft(START + timedelta(minutes=at), "approved")
    d.answered_at = d.created_at + timedelta(minutes=wait)
    m.content_due_on = india_date(d.created_at) + timedelta(days=due_in)

    moved = delivery_due_on(m, [d], d.answered_at)

    assert moved is not None and moved > india_date(d.answered_at)


@given(at=minutes, wait=waits, window=windows)
def test_the_wait_is_its_whole_days_plus_one_or_two(at, wait, window):
    """Calendar days, both ends included: the whole days held, plus one or two."""
    d = draft(START + timedelta(minutes=at), "approved")
    d.answered_at = d.created_at + timedelta(minutes=wait)

    days = days_waiting_on_brand(memo(window), [d], d.answered_at)

    assert wait // (24 * 60) + 1 <= days <= wait // (24 * 60) + 2
    if india_date(d.answered_at) == india_date(d.created_at):
        assert days == 1


@given(steps=histories, window=windows, now=minutes)
def test_the_stage_carries_the_moved_date(steps, window, now):
    m = memo(window)
    drafts = build(steps)
    when = START + timedelta(minutes=now)

    assert stage_of(m, [], None, when, drafts=drafts).work_due_on == delivery_due_on(
        m, drafts, when
    )


@given(steps=histories, window=windows, now=minutes, later=minutes)
def test_the_due_date_never_moves_earlier(steps, window, now, later):
    m = memo(window)
    drafts = build(steps)
    when = START + timedelta(minutes=now)

    first = delivery_due_on(m, drafts, when)

    assert first is not None and first >= m.content_due_on
    assert delivery_due_on(m, drafts, when + timedelta(minutes=later)) >= first


@given(steps=histories, window=windows, now=minutes)
def test_without_the_term_the_agreed_date_holds(steps, window, now):
    m = memo(window, draft_review=False)

    assert (
        delivery_due_on(m, build(steps), START + timedelta(minutes=now))
        == m.content_due_on
    )


@given(steps=histories, window=windows, now=minutes, later=minutes)
def test_answered_drafts_claim_no_more_waiting(steps, window, now, later):
    """With nothing waiting on the brand, the moved date stays put as time passes."""
    m = memo(window)
    drafts = [d for d in build(steps) if d.status != "submitted"]
    when = START + timedelta(minutes=now)

    assert delivery_due_on(m, drafts, when) == delivery_due_on(
        m, drafts, when + timedelta(minutes=later)
    )


@given(at=minutes, window=windows, cut=minutes, later=minutes)
def test_a_deal_cancelled_before_the_deadline_never_reaches_it(at, window, cut, later):
    d = draft(START + timedelta(minutes=at))
    m = memo(window)
    deadline = answer_deadline(m, d, [d])
    m.status = "cancelled"
    m.cancelled_at = min(
        d.created_at + timedelta(minutes=cut), deadline - timedelta(seconds=1)
    )

    when = deadline + timedelta(minutes=later)

    assert not is_approved(m, d, [d], when)
    assert approved_among(m, [d], when) is None
    assert answered_at(m, d, [d], when) is None  # the clock never answered it


@given(at=minutes, window=windows, due_in=st.integers(0, 60), later=minutes)
def test_a_waiting_draft_shown_in_time_never_shows_the_deal_overdue(
    at, window, due_in, later
):
    m = memo(window)
    d = draft(START + timedelta(minutes=at))
    m.content_due_on = india_date(d.created_at) + timedelta(days=due_in)
    # Any moment while it still waits, up to the instant before the clock answers.
    when = min(
        d.created_at + timedelta(minutes=later),
        answer_deadline(m, d, [d]) - timedelta(microseconds=1),
    )

    moved = delivery_due_on(m, [d], when)

    # Answered today at the latest, the creator still has the whole of tomorrow.
    assert moved is not None and moved > india_date(when)


@given(at=minutes, window=windows, later=minutes)
def test_settling_the_clocks_answer_never_moves_the_date(at, window, later):
    """Found by the fifth review: the settled branch was never exercised."""
    m = memo(window)
    d = draft(START + timedelta(minutes=at))
    deadline = answer_deadline(m, d, [d])
    when = deadline + timedelta(minutes=later)
    before = delivery_due_on(m, [d], when)

    d.status, d.auto_approved = "approved", True
    d.approved_at = d.answered_at = deadline

    assert delivery_due_on(m, [d], when) == before


@given(steps=histories, window=windows, now=minutes)
def test_the_date_never_moves_more_than_the_days_since_the_first_draft(
    steps, window, now
):
    """Distinct days: however many rounds, at most one day per calendar date."""
    m = memo(window)
    drafts = build(steps)
    when = START + timedelta(minutes=now)
    moved = delivery_due_on(m, drafts, when)
    if not drafts:
        assert moved == m.content_due_on
        return
    first = min(india_date(d.created_at) for d in drafts)
    last = max(
        india_date(when),
        *(india_date(d.created_at) for d in drafts),
        *(india_date(d.answered_at) for d in drafts if d.answered_at is not None),
    )

    assert (moved - m.content_due_on).days <= (last - first).days + 1


dues = st.integers(min_value=0, max_value=130)


def due_memo(window: int, due_in: int) -> DealMemo:
    """A memo due near the drafts, so histories reach drafts shown late too."""
    m = memo(window)
    m.content_due_on = START.date() + timedelta(days=due_in)
    return m


@given(steps=histories, window=windows, due_in=dues, now=minutes, seed=st.randoms())
def test_the_order_drafts_are_read_in_never_matters(steps, window, due_in, now, seed):
    """Found by the sixth review: the late check depends on order, and readers do not sort."""
    m = due_memo(window, due_in)
    drafts = build(steps)
    shuffled = list(drafts)
    seed.shuffle(shuffled)
    when = START + timedelta(minutes=now)

    assert delivery_due_on(m, shuffled, when) == delivery_due_on(m, drafts, when)
    assert days_held_late(m, shuffled, when) == days_held_late(m, drafts, when)


@given(steps=histories, window=windows, due_in=dues, now=minutes)
def test_a_late_draft_adds_nothing_to_the_date(steps, window, due_in, now):
    m = due_memo(window, due_in)
    drafts = build(steps)
    when = START + timedelta(minutes=now)
    if not drafts:
        return
    *earlier, last = drafts
    before = delivery_due_on(m, earlier, when)

    if india_date(last.created_at) > before:
        assert delivery_due_on(m, drafts, when) == before
    else:
        assert delivery_due_on(m, drafts, when) >= before


rounds = st.lists(
    st.tuples(st.integers(0, 6 * 24 * 60), st.integers(0, 6 * 24 * 60)),
    min_size=1,
    max_size=5,
)


@given(plan=rounds, window=windows, due_in=dues)
def test_an_answer_to_a_draft_in_time_always_leaves_the_next_day(plan, window, due_in):
    """Real rounds, one after another: whatever the creator's gaps and the brand's holds."""
    m = due_memo(window, due_in)
    drafts: list[ContentDraft] = []
    at = START
    for i, (gap, hold) in enumerate(plan):
        at += timedelta(minutes=gap)
        d = draft(at, "changes_requested", i + 1)
        d.answered_at = at + timedelta(minutes=hold)
        drafts.append(d)
        at = d.answered_at
        if shown_in_time(m, drafts, d, at):
            assert delivery_due_on(m, drafts, at) > india_date(at)
