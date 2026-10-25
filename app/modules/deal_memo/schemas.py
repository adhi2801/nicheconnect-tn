"""Request and response shapes for deal memos."""

import uuid
from datetime import date, datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator
from pydantic_core import PydanticCustomError

from app.core.literals import ensure_same_values
from app.core.taxonomy import CURRENCY
from app.core.text_flags import FieldFlag, field_flags
from app.modules.campaigns.schemas import DeliverableItems, DeliverableRead
from app.modules.deal_memo.delivery_record import (
    HAS_HISTORY,
    NO_HISTORY_YET,
    DeliveryRecord,
)
from app.modules.deal_memo.models import (
    CANCELLATION_KINDS,
    CHANGE_REQUEST_MAX_LENGTH,
    CHANGE_REQUEST_MIN_LENGTH,
    DELIVERABLES_MAX_LENGTH,
    MAX_USAGE_RIGHTS_DAYS,
    MAX_WINDOW_DAYS,
    MEMO_STATUSES,
    TERMS_MAX_LENGTH,
    DealMemo,
)
from app.modules.deal_memo.note_models import NOTE_MAX_LENGTH, NOTE_SIDES
from app.modules.deal_memo.response_times import MIN_EXAMPLES, ResponseTime
from app.modules.deal_memo.stage import DEAL_SIDES, DEAL_STAGES, DealStage

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
    deliverable_items: DeliverableItems | None = Field(
        default=None,
        description=(
            "The deliverables as a list (D-127). Left out, the campaign's own "
            "list is copied; an empty list means none"
        ),
    )
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
    deliverable_items: DeliverableItems | None = None
    fee_amount_paise: Paise | None = None
    cancellation_fee_paise: CancellationFee | None = None
    approval_window_days: WindowDays | None = None
    payment_due_days: WindowDays | None = None
    usage_rights_days: UsageRightsDays | None = None
    content_due_on: date | None = None
    disclosure_required: bool | None = None
    extra_terms: ExtraTerms | None = None

    @model_validator(mode="after")
    def at_least_one_field(self) -> MemoUpdate:
        if not self.model_fields_set:
            raise PydanticCustomError("empty_update", "Send at least one field to change")
        return self


class ChangeRequest(BaseModel):
    """What the creator wants changed, in their own words."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    message: Annotated[
        str,
        Field(
            min_length=CHANGE_REQUEST_MIN_LENGTH,
            max_length=CHANGE_REQUEST_MAX_LENGTH,
            examples=["Can we make it 2 reels instead of 3, for the same fee?"],
        ),
    ]


class MemoFields(BaseModel):
    """What a memo says by itself; `MemoRead` adds the figure agreed before it."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    application_id: uuid.UUID
    deliverables: str
    deliverable_items: list[DeliverableRead] = Field(
        description=(
            "The deliverables as a list, in order (D-127). Sealed with the "
            "terms from 25 October 2026; empty on memos made before"
        )
    )
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
    declined_at: datetime | None = Field(
        description=(
            "When the creator declined. Null otherwise, and on memos declined "
            "before 12 October 2026, when it was first kept"
        )
    )
    change_request_message: str | None = Field(
        description=(
            "What the creator last asked to change, in their words; kept after "
            "the memo is sent again. Null until a request, and on requests made "
            "before 12 October 2026"
        )
    )
    created_at: datetime
    updated_at: datetime

    @computed_field(  # type: ignore[prop-decorator]  # pydantic documents this
        description=(
            "Warnings on the free text above, worked out on every read: a request "
            "for money from a creator, or contact details before a deal is agreed "
            "(item 60). Show each beside its field; never hide the text"
        )
    )
    @property
    def text_flags(self) -> list[FieldFlag]:
        # The brand writes the memo and the creator reads it: a request for a
        # fee or deposit in its terms is the scam to catch. The two are
        # already matched, so contact details are no longer a warning.
        # `change_request_message` goes the other way, creator to brand,
        # after they were matched: a creator naming a price is ordinary and
        # contact is no longer a warning, so neither flag applies to it.
        return field_flags(
            {"deliverables": self.deliverables, "extra_terms": self.extra_terms},
            money=True,
            contact=False,
        )


class MemoRead(MemoFields):
    """A memo as the API returns it."""

    agreed_amount_paise: int | None = Field(
        description=(
            "The figure both sides agreed through a counter-offer on the "
            "application (item 44), in paise; null when none was. It pre-filled "
            "`fee_amount_paise`. When the two differ, show both: the creator "
            "accepts the memo's fee, so they see the change before they do"
        )
    )


def to_memo_read(memo: DealMemo, agreed_amount_paise: int | None) -> MemoRead:
    return MemoRead(
        **MemoFields.model_validate(memo).model_dump(),
        agreed_amount_paise=agreed_amount_paise,
    )


DealStageName = Literal[
    "draft",
    "memo_sent",
    "agreed",
    "in_progress",
    "payment",
    "finished",
    "declined",
    "cancelled",
]
DealSide = Literal["brand", "creator"]

ensure_same_values("DealStageName", DealStageName, DEAL_STAGES)
ensure_same_values("DealSide", DealSide, DEAL_SIDES)


class MemoWithStageRead(MemoRead):
    """A memo, with where the deal stands and whose move it is (D-076).

    Worked out from the memo, its proof and its payment as of the request,
    never stored. The five stages a deal passes through are `memo_sent`,
    `agreed`, `in_progress`, `payment`, `finished`; `draft`, `declined` and
    `cancelled` sit outside them. A barter deal is `finished` once its work
    is approved; a paid one only when the creator confirms the money arrived.
    """

    stage: DealStageName
    waiting_on: DealSide | None = Field(
        description="The side whose move it is; null once the deal has ended"
    )
    has_open_dispute: bool


def with_stage(
    memo: DealMemo, found: DealStage, agreed_amount_paise: int | None
) -> MemoWithStageRead:
    return MemoWithStageRead(
        **to_memo_read(memo, agreed_amount_paise).model_dump(),
        stage=found.stage,
        waiting_on=found.waiting_on,
        has_open_dispute=found.has_open_dispute,
    )


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
    distinct_brands: int = Field(
        description=(
            "How many different brands the completed deals were with. Show it beside "
            "the figures: twelve deals with one brand say less than twelve across nine"
        )
    )


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
        distinct_brands=record.distinct_brands,
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
    notes_unchanged: bool | None = Field(
        default=None,
        description=(
            "Null when the deal has no notes; otherwise whether every note still "
            "matches the fingerprint sealed for it (D-128)"
        ),
    )
    latest_seal: str | None = Field(description="Save this to detect a later rewrite")
    entries: list[DealRecordEntryRead]


# --- a deal's proof in a daily checkpoint (D-060) ------------------------------


class CheckpointTimestampRead(BaseModel):
    """One authority's signed statement that the day's root existed."""

    authority: Literal["digicert", "sectigo"]
    signed_at: datetime = Field(
        description="The authority's own time, from inside the token"
    )
    token_base64: str = Field(
        description=(
            "The RFC 3161 token exactly as issued, base64. Check it with "
            "`openssl ts -verify -in token.tsr -data root.bin -CAfile <roots>`"
        )
    )


class DealRecordProofRead(BaseModel):
    """How this deal's record is tied to a day's root, and who stamped that root.

    Recompute the root from `seal` and `audit_path` (RFC 6962), and check each
    token signs it: then the record as it stood that day did not rest on our
    word. `docs/DEAL_RECORD_VERIFY.md` walks through it.
    """

    deal_memo_id: uuid.UUID
    checkpoint_date: date = Field(description="Named by its date in Tamil Nadu")
    covers_until: str = Field(
        description="Entries recorded before this moment are covered",
        examples=["2026-09-26T18:30:00.000000Z"],
    )
    algorithm: Literal["rfc6962-sha256"] = "rfc6962-sha256"
    leaf_format: Literal["deal_memo_id (16 bytes) + seal (32 bytes)"] = (
        "deal_memo_id (16 bytes) + seal (32 bytes)"
    )
    leaf_count: int
    leaf_index: int
    seal: str = Field(description="This deal's latest seal as of the cut-off, hex")
    audit_path: list[str] = Field(
        description="Sibling hashes from the leaf to the root, hex"
    )
    merkle_root: str = Field(
        description="The day's root, hex; what the authorities signed"
    )
    stamped: bool = Field(
        description="False while no authority has stamped the root yet: a visible gap"
    )
    timestamps: list[CheckpointTimestampRead]


# --- typical response times (D-077) --------------------------------------------------------


class ResponseTimeRead(BaseModel):
    """How long one kind of answer usually takes, from the deal record.

    `median_hours` is null until there are five examples (D-071). **Null
    means "not enough to say" and must never be shown as zero.** `examples`
    is always returned so the figure can be weighed.
    """

    examples: int = Field(ge=0)
    median_hours: float | None
    min_examples: int = Field(description="Examples needed before a figure is shown")


def to_response_time_read(found: ResponseTime) -> ResponseTimeRead:
    return ResponseTimeRead(
        examples=found.examples,
        median_hours=found.median_hours,
        min_examples=MIN_EXAMPLES,
    )


class BrandResponseTimesRead(BaseModel):
    """How long creators wait for this brand to decide on their work.

    An approval by the clock counts, at the moment the window ended.
    """

    brand_id: uuid.UUID
    work_reviewed: ResponseTimeRead


class CreatorResponseTimesRead(BaseModel):
    """How long brands wait for this creator to answer a memo, and to confirm
    a payment arrived."""

    creator_id: uuid.UUID
    memo_answered: ResponseTimeRead
    payment_confirmed: ResponseTimeRead


# --- deal notes (item 17, D-128) ------------------------------------------------

NoteSide = Literal["brand", "creator"]

ensure_same_values("NoteSide", NoteSide, NOTE_SIDES)


class NoteCreate(BaseModel):
    """A note one side writes on the deal, sealed onto its record."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    body: str = Field(
        min_length=1,
        max_length=NOTE_MAX_LENGTH,
        examples=["Can the second reel go up on Saturday instead of Friday?"],
    )


class NoteRead(BaseModel):
    """A note, as both sides read it. It never changes once written."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    deal_memo_id: uuid.UUID
    author_side: NoteSide = Field(description="Who wrote it")
    body: str
    created_at: datetime

    @computed_field(  # type: ignore[prop-decorator]  # pydantic documents this
        description=(
            "Warnings on the note, worked out on every read: a request for money "
            "from a creator. The two are matched, so contact details are not a "
            "warning. Show each beside the note; never hide it"
        )
    )
    @property
    def text_flags(self) -> list[FieldFlag]:
        # A brand's words reach a creator: a fee request is the scam to catch.
        return field_flags(
            {"body": self.body}, money=self.author_side == "brand", contact=False
        )
