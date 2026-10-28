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
- **The brand's waiting is the brand's.** Each draft moves the creator's
  due date by every Tamil Nadu calendar day the brand held it, from the day
  it was shown to the day it was answered, both included, before "on time"
  is judged. Calendar days, because a due date is a date and lateness is
  judged by date; the answer day too, so the creator always has the whole
  day after an answer (Adhi's choices of 28 October 2026, after the third
  and fourth reviews). So asking for changes again and again can never
  push a creator late (each round moves the date at least a day), an
  approval at 23:59 leaves the creator the next day, and a draft still
  waiting counts as if answered today, so it never shows the deal overdue.
  The clock answers at the midnight that ends the brand's last day, so that
  last day is its answer day. The creator's own rework time stays theirs,
  and a draft shown after the due date is late however long it waits.
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
    """Calendar days, in Tamil Nadu, the brand held the memo's drafts, up to `now`.

    For each draft: the days from the one it was shown to the one it was
    answered, both included; today while it still waits; never past the
    day of a cancellation.
    """
    total = 0
    for draft in drafts:
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
        total += max(0, (answer_day - india_date(draft.created_at)).days) + 1
    return total


def delivery_due_on(
    memo: DealMemo, drafts: Sequence[ContentDraft], now: datetime
) -> date | None:
    """The date the work is due by, with every day the brand held a draft added."""
    if memo.content_due_on is None or not memo.draft_review:
        return memo.content_due_on
    return memo.content_due_on + timedelta(days=days_waiting_on_brand(memo, drafts, now))
