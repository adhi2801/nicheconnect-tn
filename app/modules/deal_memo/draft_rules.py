"""Whether a draft is approved, by the brand or by the clock (item 27, D-140). Pure.

Here, apart from draft_service, so the deal's stage and proof's own check
read the same rule without importing the service that writes drafts.
"""

from collections.abc import Sequence
from datetime import datetime

from app.modules.deal_memo.draft_models import ContentDraft
from app.modules.deal_memo.models import DealMemo
from app.modules.deal_memo.review_clock import approval_deadline


def is_approved(
    memo: DealMemo, draft: ContentDraft, history: Sequence[ContentDraft], now: datetime
) -> bool:
    """Approved, by the brand or by the clock, as of `now`. Pure."""
    if draft.status == "approved":
        return True
    return draft.status == "submitted" and now >= approval_deadline(memo, draft, history)


def approved_among(
    memo: DealMemo, drafts: Sequence[ContentDraft], now: datetime
) -> ContentDraft | None:
    """The memo's approved draft as of `now`, by the clock too, or None. Pure."""
    return next((d for d in drafts if is_approved(memo, d, drafts, now)), None)
