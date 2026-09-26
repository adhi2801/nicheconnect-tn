"""Request and response shapes for deal memos."""

import uuid
from datetime import date, datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic_core import PydanticCustomError

from app.core.literals import ensure_same_values
from app.core.taxonomy import CURRENCY
from app.modules.deal_memo.delivery_record import (
    HAS_HISTORY,
    NO_HISTORY_YET,
    DeliveryRecord,
)
from app.modules.deal_memo.models import (
    CANCELLATION_KINDS,
    DELIVERABLES_MAX_LENGTH,
    MAX_USAGE_RIGHTS_DAYS,
    MAX_WINDOW_DAYS,
    MEMO_STATUSES,
    TERMS_MAX_LENGTH,
)

MemoStatus = Literal[
    "draft", "sent", "change_requested", "accepted", "declined", "cancelled"
]
CancellationKind = Literal[
    "withdrawn_early", "cancelled_by_brand", "cancelled_by_creator"
]

ensure_same_values("MemoStatus", MemoStatus, MEMO_STATUSES)
ensure_same_values("CancellationKind", CancellationKind, CANCELLATION_KINDS)

Deliverables = Annotated[
    str,
    Field(
        min_length=1,
        max_length=DELIVERABLES_MAX_LENGTH,
        examples=["3 Instagram reels, 1 story set"],
    ),
]
Paise = Annotated[
    int,
    Field(gt=0, le=10_000_000_000, description="Whole paise, e.g. 800000 is Rs 8,000"),
]
CancellationFee = Annotated[int, Field(ge=0, le=10_000_000_000)]
WindowDays = Annotated[int, Field(ge=1, le=MAX_WINDOW_DAYS)]
UsageRightsDays = Annotated[int, Field(ge=1, le=MAX_USAGE_RIGHTS_DAYS)]
ExtraTerms = Annotated[str, Field(max_length=TERMS_MAX_LENGTH)]


class MemoCreate(BaseModel):
    """What a brand sends to draft a memo for an accepted application."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    deliverables: Deliverables
    # Required for paid and local-business campaigns, refused for barter.
    # The campaign decides, so the service checks it, not this schema.
    fee_amount_paise: Paise | None = None
    cancellation_fee_paise: CancellationFee = 0
    approval_window_days: WindowDays = 7
    payment_due_days: WindowDays = 7
    usage_rights_days: UsageRightsDays | None = None
    content_due_on: date | None = None
    disclosure_required: bool = True
    extra_terms: ExtraTerms | None = None


class MemoUpdate(BaseModel):
    """Changes to a memo the brand still holds."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    deliverables: Deliverables | None = None
    fee_amount_paise: Paise | None = None
    cancellation_fee_paise: CancellationFee | None = None
    approval_window_days: WindowDays | None = None
    payment_due_days: WindowDays | None = None
    usage_rights_days: UsageRightsDays | None = None
    content_due_on: date | None = None
    disclosure_required: bool | None = None
    extra_terms: ExtraTerms | None = None

    @model_validator(mode="after")
    def at_least_one_field(self) -> "MemoUpdate":
        if not self.model_fields_set:
            raise PydanticCustomError("empty_update", "Send at least one field to change")
        return self


class ChangeRequest(BaseModel):
    """What the creator wants changed, in their own words."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    message: Annotated[
        str,
        Field(
            min_length=5,
            max_length=1000,
            examples=["Can we make it 2 reels instead of 3, for the same fee?"],
        ),
    ]


class MemoRead(BaseModel):
    """A memo as the API returns it."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    application_id: uuid.UUID
    deliverables: str
    fee_amount_paise: int | None
    currency: Literal["INR"] = CURRENCY
    cancellation_fee_paise: int
    approval_window_days: int
    payment_due_days: int
    usage_rights_days: int | None
    content_due_on: date | None
    disclosure_required: bool
    extra_terms: str | None
    status: MemoStatus
    revision_count: int
    sent_at: datetime | None
    accepted_at: datetime | None
    work_started_at: datetime | None
    cancelled_at: datetime | None
    cancellation_kind: CancellationKind | None
    created_at: datetime
    updated_at: datetime


DeliveryStatus = Literal["new_creator_no_history_yet", "has_delivery_history"]

ensure_same_values("DeliveryStatus", DeliveryStatus, (NO_HISTORY_YET, HAS_HISTORY))


class CreatorDeliveryRead(BaseModel):
    """How a creator delivers, from what happened rather than from opinions.

    The mirror of a brand's payment record (D-038). The shares are `null`
    until three scored deals have completed. **Null means "not enough to
    say" and must never be shown as zero**: the two mean opposite things.

    `currently_overdue` is reported whatever the status, so "new" can never
    hide work a brand is still waiting for. Barter deals are shown in their
    own counts and never scored (D-026).
    """

    creator_id: uuid.UUID
    status: DeliveryStatus
    deals_completed: int = Field(
        description="Scored (non-barter) deals that reached an outcome"
    )
    deals_delivered: int
    deals_not_delivered: int = Field(
        description=(
            "Cancelled by the creator after work had started, or nothing "
            "delivered 14 days after the agreed date"
        )
    )
    currently_overdue: int = Field(
        description="Deals past their agreed date with nothing delivered yet"
    )
    delivered_on_time_share: float | None = Field(
        description=(
            "Share of completed deals delivered by the agreed date, judged by "
            "the first submission. Null below three completed deals"
        )
    )
    disclosure_confirmed_share: float | None = Field(
        description=(
            "Of delivered deals that required an ad disclosure, the share where "
            "the creator confirmed it was on the post. The creator's statement, "
            "not a judgement of compliance. Null below three completed deals, "
            "or when no delivered deal required one"
        )
    )
    barter_deals_delivered: int
    barter_deals_not_delivered: int


def to_delivery_read(record: DeliveryRecord) -> CreatorDeliveryRead:
    return CreatorDeliveryRead(
        creator_id=record.creator_id,
        status=record.status,
        deals_completed=record.deals_completed,
        deals_delivered=record.deals_delivered,
        deals_not_delivered=record.deals_not_delivered,
        currently_overdue=record.currently_overdue,
        delivered_on_time_share=record.delivered_on_time_share,
        disclosure_confirmed_share=record.disclosure_confirmed_share,
        barter_deals_delivered=record.barter_deals_delivered,
        barter_deals_not_delivered=record.barter_deals_not_delivered,
    )


# --- the deal record (D-057) -----------------------------------------------


class DealRecordEntryRead(BaseModel):
    """One sealed step. `facts` holds figures and fingerprints, never typed text."""

    sequence: int
    kind: str
    actor_role: Literal["brand", "creator", "system"] = Field(
        description="`system` is the deal's own rules acting, such as approval at the deadline"
    )
    actor_account_sha256: str | None = Field(
        description=(
            "SHA-256 of the acting account's id, part of the seal. Hash your "
            "own account id to recognise your entries; null for `system`"
        )
    )
    # Strings, in exactly the spelling the seal was computed over (UTC, to
    # the microsecond, ending in Z), so the seals can be checked from this
    # JSON alone. The API's usual spelling drops the microseconds.
    occurred_at: str = Field(
        description="When it took effect", examples=["2026-09-26T06:30:00.000000Z"]
    )
    recorded_at: str = Field(
        description="When we wrote it down", examples=["2026-09-26T06:30:00.000000Z"]
    )
    facts: dict[str, Any]
    previous_seal: str = Field(
        description="Hex SHA-256 of the entry before; zeros for the first"
    )
    seal: str = Field(description="Hex SHA-256 sealing this entry to the one before")


class DealRecordRead(BaseModel):
    """A deal's whole record, and whether it still holds together.

    `intact` is our own check. The point of the seals is that you need not
    take our word for it: `docs/DEAL_RECORD_VERIFY.md` shows how to check them
    yourself, and saving `latest_seal` lets you catch a rewrite later.
    """

    deal_memo_id: uuid.UUID
    algorithm: Literal["deal-record/v1"] = "deal-record/v1"
    intact: bool
    first_broken_sequence: int | None = Field(
        description="The first entry that does not match, if any"
    )
    terms_unchanged_since_accepted: bool | None = Field(
        description="Null until accepted; then whether today's terms are the accepted ones"
    )
    latest_seal: str | None = Field(description="Save this to detect a later rewrite")
    entries: list[DealRecordEntryRead]
