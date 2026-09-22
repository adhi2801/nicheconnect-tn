"""What is waiting on someone: the one shape every module reports in.

Each module says what of its own is waiting on a brand or a creator, in its
`attention.py`. `app/modules/auth/attention_service.py` gathers them for
`GET /api/v1/me/attention`, the way the data export gathers sections, so no
module has to know about the others.

It is the pull side of the reminders D-029 planned. Those wait on a job
runner; this answers whenever someone opens the app. Nothing here is
stored: every item is worked out from the records as they stand, so an item
disappears the moment the thing it asks for is done.

The words belong to the frontend, in Tamil and English (ux.md); an item
carries a kind code and the facts, never a sentence.
"""

import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date

# What a brand can be asked to do.
BRAND_KINDS: tuple[str, ...] = (
    "respond_to_dispute",
    "pay_creator",
    "review_proof",
    "revise_memo",
    "draft_memo",
    "review_applications",
)
# What a creator can be asked to do, or needs to know.
CREATOR_KINDS: tuple[str, ...] = (
    "respond_to_dispute",
    "confirm_payment",
    "payment_overdue",
    "resubmit_work",
    "deliver_work",
    "answer_memo",
)
# Between two items due the same day, the one about money or a dispute
# first: those are the ones that turn into a record against somebody.
_PRIORITY = {
    kind: rank
    for rank, kind in enumerate(
        (
            "respond_to_dispute",
            "pay_creator",
            "confirm_payment",
            "payment_overdue",
            "review_proof",
            "resubmit_work",
            "deliver_work",
            "answer_memo",
            "revise_memo",
            "draft_memo",
            "review_applications",
        )
    )
}

# Enough for a real day's work; the counts always cover everything.
MAX_ITEMS = 50


@dataclass(frozen=True)
class AttentionItem:
    """One thing waiting on someone, with the facts needed to act on it."""

    kind: str
    # The Tamil Nadu date it is due by, or None when nothing sets a date.
    due_on: date | None
    campaign_id: uuid.UUID
    campaign_title: str
    # The other side: a creator's handle for a brand, a brand's name for a
    # creator. None when the item is about many people (a count).
    counterparty: str | None = None
    application_id: uuid.UUID | None = None
    memo_id: uuid.UUID | None = None
    proof_id: uuid.UUID | None = None
    amount_paise: int | None = None
    # For an item that stands for several things at once.
    count: int | None = None


@dataclass(frozen=True)
class AttentionList:
    """Everything waiting on one account, as the endpoint returns it."""

    role: str
    as_of: date
    # Items per kind, every kind for the role present, zeros included.
    counts: dict[str, int]
    # The most urgent first, at most MAX_ITEMS of them.
    items: list[AttentionItem]
    total: int
    truncated: bool


def by_urgency(items: Iterable[AttentionItem]) -> list[AttentionItem]:
    """Overdue first, then the soonest due, then anything without a date.

    Ties go to money and disputes first, then to a stable id, so the same
    records always give the same order.
    """

    def key(item: AttentionItem) -> tuple[bool, date, int, str]:
        tie = item.proof_id or item.memo_id or item.application_id or item.campaign_id
        return (
            item.due_on is None,
            item.due_on or date.max,
            _PRIORITY[item.kind],
            str(tie),
        )

    return sorted(items, key=key)
