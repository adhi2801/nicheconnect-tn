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
- **The brand's waiting is the brand's.** Every whole day a draft waited
  for the brand's answer moves the creator's due date by a day before "on
  time" is judged, so a slow brand cannot make a creator look late.
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


def is_approved(
    memo: DealMemo, draft: ContentDraft, history: Sequence[ContentDraft], now: datetime
) -> bool:
    """Approved, by the brand or by the clock, as of `now`."""
    if draft.status == "approved":
        return True
    return draft.status == "submitted" and now >= answer_deadline(memo, draft, history)


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
        return deadline if now >= deadline else None
    return None


def days_waiting_on_brand(
    memo: DealMemo, drafts: Sequence[ContentDraft], now: datetime
) -> int:
    """Whole Tamil Nadu days the memo's drafts waited for the brand, up to `now`."""
    total = 0
    for draft in drafts:
        end = answered_at(memo, draft, drafts, now) or now
        total += max(0, (india_date(end) - india_date(draft.created_at)).days)
    return total


def delivery_due_on(
    memo: DealMemo, drafts: Sequence[ContentDraft], now: datetime
) -> date | None:
    """The date the work is due by, with every day drafts waited on the brand added."""
    if memo.content_due_on is None or not memo.draft_review:
        return memo.content_due_on
    return memo.content_due_on + timedelta(days=days_waiting_on_brand(memo, drafts, now))
