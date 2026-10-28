"""When a draft is answered, and what its waiting does to the deal (item 27, D-140). Pure.

Here, apart from draft_service, so the deal's stage, proof's own check and
the delivery record read the same rules without importing the service that
writes drafts.

Two rules on top of proof's clock (D-025, `review_clock`), Adhi's choices of
27 October 2026 after the independent review:

- **Every draft gets at least MIN_ANSWER_DAYS whole days.** D-025 still
  holds, so asking again buys the brand no more time; but a draft shown
  long after the clock restarted is not approved the moment it arrives, so
  nothing is approved that the brand had no chance to see.
- **The brand's waiting is the brand's.** The creator's due date moves by
  every Tamil Nadu calendar day the brand held a draft shown in time, from
  the day it was shown to the day it was answered, both included, before
  "on time" is judged. Adhi's choices of 28 October 2026, after the third
  to sixth independent reviews:
  - calendar days, because a due date is a date and lateness is judged by
    date; the answer day too, so the creator always has the whole day after
    an answer: asking for changes again and again can never push a creator
    late, an approval at 23:59 leaves the creator the next day, and a draft
    shown in time that still waits counts as answered today, so it never
    shows the deal overdue;
  - each date once however many rounds it held, so rounds cannot be
    stacked into extra days;
  - a draft shown after the due date (as moved so far) moves nothing, so
    lateness cannot be washed out; the brand's days on it extend only the
    "not delivered" limit, because proof has to wait for its answer.
  The clock answers at the midnight that ends the brand's last day, so that
  last day is its answer day. The creator's own rework time stays theirs.
- **A deal cancelled before a deadline never reaches it.** A draft still
  waiting when the deal was cancelled is never approved by the clock, and
  its waiting stops at the cancellation.
"""

from collections.abc import Sequence
from datetime import date, datetime, time, timedelta

from app.core.clock import IST, india_date
from app.modules.deal_memo.draft_models import ContentDraft
from app.modules.deal_memo.models import DealMemo
from app.modules.deal_memo.review_clock import approval_last_day

MIN_ANSWER_DAYS = 2


def answer_last_day(
    memo: DealMemo, draft: ContentDraft, history: Sequence[ContentDraft]
) -> date:
    """The last whole day, in Tamil Nadu, the brand has to answer this draft."""
    return max(
        approval_last_day(memo, draft, history),
        india_date(draft.created_at) + timedelta(days=MIN_ANSWER_DAYS),
    )


def answer_deadline(
    memo: DealMemo, draft: ContentDraft, history: Sequence[ContentDraft]
) -> datetime:
    """When an unanswered draft approves itself: midnight after its last day."""
    last_day = answer_last_day(memo, draft, history)
    return datetime.combine(last_day + timedelta(days=1), time.min, tzinfo=IST)


def agreed_at(memo: DealMemo, moment: datetime) -> bool:
    """Whether the deal was still agreed at `moment`: accepted, or cancelled only later.

    Cancelled at the very moment: still agreed, so a deadline and a
    cancellation at the same instant leave the clock's answer standing.
    """
    if memo.status == "accepted":
        return True
    return (
        memo.status == "cancelled"
        and memo.cancelled_at is not None
        and memo.cancelled_at >= moment
    )


def is_approved(
    memo: DealMemo, draft: ContentDraft, history: Sequence[ContentDraft], now: datetime
) -> bool:
    """Approved, by the brand or by the clock, as of `now`."""
    if draft.status == "approved":
        return True
    if draft.status != "submitted":
        return False
    deadline = answer_deadline(memo, draft, history)
    return now >= deadline and agreed_at(memo, deadline)


def approved_among(
    memo: DealMemo, drafts: Sequence[ContentDraft], now: datetime
) -> ContentDraft | None:
    """The memo's approved draft as of `now`, by the clock too, or None."""
    return next((d for d in drafts if is_approved(memo, d, drafts, now)), None)


def answered_at(
    memo: DealMemo, draft: ContentDraft, history: Sequence[ContentDraft], now: datetime
) -> datetime | None:
    """When the brand answered, or the clock did; None while it still waits."""
    if draft.answered_at is not None:
        return draft.answered_at
    if draft.status == "submitted":
        deadline = answer_deadline(memo, draft, history)
        return deadline if now >= deadline and agreed_at(memo, deadline) else None
    return None


def days_waiting_on_brand(
    memo: DealMemo, drafts: Sequence[ContentDraft], now: datetime
) -> int:
    """Distinct Tamil Nadu dates the brand held a draft shown in time, up to `now`."""
    in_time, _late, _ids = _held(memo, drafts, now)
    return len(in_time)


def days_held_late(memo: DealMemo, drafts: Sequence[ContentDraft], now: datetime) -> int:
    """Distinct dates the brand held late drafts: added to the "not delivered" limit."""
    return due_and_late_days(memo, drafts, now)[1]


def due_and_late_days(
    memo: DealMemo, drafts: Sequence[ContentDraft], now: datetime
) -> tuple[date | None, int]:
    """The moved due date and the days the brand held late drafts, in one pass.

    A late draft never shares a date with one shown in time: after any answer
    to a draft in time the due date is past that day, so a later draft shown
    late starts after it, and every later draft is late too.
    """
    if memo.content_due_on is None or not memo.draft_review:
        return memo.content_due_on, 0
    in_time, late, _ids = _held(memo, drafts, now)
    return memo.content_due_on + timedelta(days=len(in_time)), len(late)


def shown_in_time(
    memo: DealMemo, drafts: Sequence[ContentDraft], draft: ContentDraft, now: datetime
) -> bool:
    """Whether this draft was shown by the due date as the drafts before it moved it."""
    return draft.id in _held(memo, drafts, now)[2]


def _held(
    memo: DealMemo, drafts: Sequence[ContentDraft], now: datetime
) -> tuple[set[date], set[date], set[object]]:
    """The dates the brand held drafts shown in time, those it held late ones, and the in-time ids.

    Drafts are taken in the order shown, whatever order they were read in.
    One is in time if shown on or before the due date as the drafts before it
    moved it. Its dates run from the day it was shown to the day it was
    answered, both included (today while it waits), never past the day of a
    cancellation; each date counts once however many rounds it held.
    """
    in_time: set[date] = set()
    late: set[date] = set()
    ids: set[object] = set()
    for draft in sorted(drafts, key=lambda d: (d.created_at, d.id)):
        shown = india_date(draft.created_at)
        end = answered_at(memo, draft, drafts, now)
        if end is None:
            answer_day = india_date(now)  # still waiting: as if answered today
        elif draft.auto_approved or draft.status == "submitted":
            # The clock answers at the midnight that ends the brand's last day.
            answer_day = india_date(end - timedelta(microseconds=1))
        else:
            answer_day = india_date(end)
        if memo.cancelled_at is not None:
            answer_day = min(answer_day, india_date(memo.cancelled_at))
        days = {
            shown + timedelta(days=offset)
            for offset in range(max(0, (answer_day - shown).days) + 1)
        }
        if memo.content_due_on is not None and shown > memo.content_due_on + timedelta(
            days=len(in_time)
        ):
            late |= days  # shown late: the brand's time cannot wash that out
        else:
            in_time |= days
            ids.add(draft.id)
    return in_time, late, ids


def delivery_due_on(
    memo: DealMemo, drafts: Sequence[ContentDraft], now: datetime
) -> date | None:
    """The date the work is due by, with every day the brand held a draft in time added."""
    return due_and_late_days(memo, drafts, now)[0]
