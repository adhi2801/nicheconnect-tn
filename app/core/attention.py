"""What is waiting on someone: the one shape every module reports in.

Each module says what of its own is waiting on a brand or a creator, in its
`attention.py`. `app/modules/me/attention_service.py` gathers them for
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
from datetime import date, datetime

# A sign-in to the account in the last 7 days, from a session other than
# the one asking (item 81, D-114). For brands and creators alike. It has no
# date to be due by, and is listed before everything else: if it was not
# them, someone else is inside the account, and every other item is theirs.
NEW_SIGN_IN = "new_sign_in"
# The account itself waiting its 30 days to be deleted (item 6, D-122), or
# held at the end by a deal, until it is erased or cancelled: due the day it
# takes effect, so a deletion that was not the owner's is in front of them
# while it can still be cancelled.
DELETION_PENDING = "deletion_pending"

# What a brand can be asked to do.
BRAND_KINDS: tuple[str, ...] = (
    "respond_to_dispute",
    "pay_creator",
    "review_proof",
    # A draft shown before posting, waiting for the brand (item 27).
    "review_draft",
    "revise_memo",
    "draft_memo",
    "review_applications",
    # The brand's own domain (item 74, D-106): the record was not found, the
    # verification lapsed, or the token expired before it was found.
    "fix_domain_record",
    "domain_lapsed",
    "domain_claim_expired",
    # A new phone number waiting its 72 hours (item 80, D-108).
    "phone_change_pending",
    # The account waiting its 30 days to be deleted (item 6, D-122).
    DELETION_PENDING,
    NEW_SIGN_IN,
)
# What a creator can be asked to do, or needs to know.
CREATOR_KINDS: tuple[str, ...] = (
    "respond_to_dispute",
    "confirm_payment",
    "payment_overdue",
    "resubmit_work",
    "deliver_work",
    # A deal agreed with a draft review: show one, or change it (item 27).
    "show_draft",
    "revise_draft",
    "answer_memo",
    "answer_invitation",
    # A new UPI ID set and waiting its 24 hours (item 82, D-107): due the
    # day brands start to see it, so a change that was not the creator's is
    # in front of them while it can still be cancelled.
    "upi_change_pending",
    # A new phone number waiting its 72 hours (item 80, D-108): due the day
    # it takes over the login, so a change that was not theirs is in front
    # of them while it can still be cancelled.
    "phone_change_pending",
    DELETION_PENDING,
    NEW_SIGN_IN,
)
# Between two items due the same day, the one about money or a dispute
# first: those are the ones that turn into a record against somebody. A
# waiting phone number before all: if it was not them, it is the whole
# account, as is a waiting deletion; then a waiting UPI ID, where a
# creator's money would go.
_PRIORITY = {
    kind: rank
    for rank, kind in enumerate(
        (
            NEW_SIGN_IN,
            DELETION_PENDING,
            "phone_change_pending",
            "upi_change_pending",
            "respond_to_dispute",
            "pay_creator",
            "confirm_payment",
            "payment_overdue",
            "review_proof",
            "review_draft",
            "resubmit_work",
            "revise_draft",
            "deliver_work",
            "show_draft",
            "answer_memo",
            "answer_invitation",
            "revise_memo",
            "draft_memo",
            "review_applications",
            "fix_domain_record",
            "domain_lapsed",
            "domain_claim_expired",
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
    # None for an item about the account itself rather than a campaign:
    # the brand's domain (item 74), a creator's waiting UPI ID (item 82),
    # a waiting phone number (item 80), a waiting deletion (item 6).
    campaign_id: uuid.UUID | None
    campaign_title: str | None
    # The other side: a creator's handle for a brand, a brand's name for a
    # creator. None when the item is about many people (a count).
    counterparty: str | None = None
    application_id: uuid.UUID | None = None
    memo_id: uuid.UUID | None = None
    proof_id: uuid.UUID | None = None
    draft_id: uuid.UUID | None = None
    amount_paise: int | None = None
    # For an item that stands for several things at once.
    count: int | None = None
    # The brand's domain, for the domain items.
    domain: str | None = None
    # For a new sign-in (D-114): which session, when, on what the app said
    # it is, and how it was proven.
    session_id: uuid.UUID | None = None
    signed_in_at: datetime | None = None
    device_platform: str | None = None
    device_label: str | None = None
    signed_in_with: str | None = None


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
    """New sign-ins first; then overdue, the soonest due, and anything without a date.

    Ties go to money and disputes first, then to a stable id, so the same
    records always give the same order.
    """

    def key(item: AttentionItem) -> tuple[bool, bool, date, int, str]:
        tie = (
            item.proof_id
            or item.draft_id
            or item.memo_id
            or item.application_id
            or item.campaign_id
            or item.domain
            or item.session_id
        )
        return (
            item.kind != NEW_SIGN_IN,
            item.due_on is None,
            item.due_on or date.max,
            _PRIORITY[item.kind],
            str(tie),
        )

    return sorted(items, key=key)
