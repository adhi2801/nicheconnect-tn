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
- **The brand's waiting is the brand's.** Every Tamil Nadu calendar day a
  draft spent waiting for the brand, past the day it was shown, moves the
  creator's due date by a day before "on time" is judged. Calendar days,
  because a due date is a date and lateness is judged by date (Adhi's
  choice, 27 October 2026, after the third review): a draft shown on the
  due day and answered the next morning moves the date to that morning's
  day, so a waiting brand can never make a creator late. In the creator's
  favour at the edges: 23:55 to 00:05 moves a day, and silence through a
  7-day window moves eight, the day it was shown included.
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
    """Whether the deal was still agreed at `moment`: accepted, or cancelled only later."""
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
    """Calendar days, in Tamil Nadu, the memo's drafts waited for the brand, up to `now`.

    For each draft: the days from the one it was shown to the one it was
    answered (or to today while it waits), never past a cancellation. A draft
    answered without a recorded moment claims no wait.
    """
    total = 0
    for draft in drafts:
        end = answered_at(memo, draft, drafts, now)
        if end is None:
            if draft.status != "submitted":
                continue
            end = now
        if memo.cancelled_at is not None:
            end = min(end, memo.cancelled_at)
        total += max(0, (india_date(end) - india_date(draft.created_at)).days)
    return total


def delivery_due_on(
    memo: DealMemo, drafts: Sequence[ContentDraft], now: datetime
) -> date | None:
    """The date the work is due by, with every day drafts waited on the brand added."""
    if memo.content_due_on is None or not memo.draft_review:
        return memo.content_due_on
    return memo.content_due_on + timedelta(days=days_waiting_on_brand(memo, drafts, now))
