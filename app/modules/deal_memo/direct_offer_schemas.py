"""Request and response shapes for direct offers (D-189)."""

import uuid
from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.core.literals import ensure_same_values
from app.modules.auth.schemas import (
    BrandEmail,
    BrandName,
    DateOfBirth,
    IndianMobile,
    LoginTokens,
    OtpCode,
)
from app.modules.campaigns.schemas import DeliverableItems, DeliverableRead
from app.modules.deal_memo.direct_offer_models import (
    DIRECT_OFFER_STATUSES,
    HEX_SHA256_PATTERN,
)
from app.modules.deal_memo.schemas import (
    CancellationFee,
    Deliverables,
    ExtraTerms,
    Paise,
    UsageRightsDays,
    WindowDays,
)

DirectOfferStatus = Literal["sent", "accepted", "withdrawn", "stopped", "expired"]
ensure_same_values("DirectOfferStatus", DirectOfferStatus, DIRECT_OFFER_STATUSES)

TermsSha256 = Annotated[
    str,
    Field(
        pattern=HEX_SHA256_PATTERN,
        description="The SHA-256 of the offer's terms, as the deal record seals them",
        examples=["9f2c" + "0" * 60],
    ),
]


class DirectOfferCreate(BaseModel):
    """What a creator sends: the terms a memo carries, and who they are for."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    brand_name: BrandName = Field(
        description="The brand's name as you know it; the brand confirms or corrects it"
    )
    brand_phone: IndianMobile = Field(
        description=(
            "The brand's WhatsApp number. Only this number can accept: the code "
            "that accepts goes to it. Never shown to anyone, and kept only while "
            "the offer waits"
        )
    )
    deliverables: Deliverables
    deliverable_items: DeliverableItems = []
    fee_amount_paise: Paise
    cancellation_fee_paise: CancellationFee = 0
    approval_window_days: WindowDays = 7
    payment_due_days: WindowDays = 7
    usage_rights_days: UsageRightsDays | None = None
    content_due_on: date = Field(
        description="The Tamil Nadu day the work is due: from today, at most a year ahead"
    )
    disclosure_required: bool = True
    draft_review: bool = Field(
        default=False,
        description="A draft is shown and approved before posting (item 27)",
    )
    extra_terms: ExtraTerms | None = None


class DirectOfferTerms(BaseModel):
    """The terms of an offer, exactly as the memo will hold them."""

    model_config = ConfigDict(from_attributes=True)

    deliverables: str
    deliverable_items: list[DeliverableRead]
    fee_amount_paise: int
    currency: Literal["INR"]
    cancellation_fee_paise: int
    approval_window_days: int
    payment_due_days: int
    usage_rights_days: int | None
    content_due_on: date
    disclosure_required: bool
    draft_review: bool
    extra_terms: str | None
    terms_sha256: TermsSha256


class DirectOfferRead(DirectOfferTerms):
    """One of the creator's own offers, as their sent list shows it."""

    id: uuid.UUID
    status: DirectOfferStatus = Field(
        description=(
            "`sent` while it waits, `accepted`, `withdrawn` by you, `stopped` by "
            "the number's holder, or `expired` after 14 days. Clients tolerate "
            "values they do not know"
        )
    )
    brand_name: str | None = Field(
        description=(
            "The name you gave the brand, while the offer waits; null once it "
            "ended, when it is erased (the accepted deal names the brand)"
        )
    )
    sent_at: datetime
    expires_at: datetime
    opened_at: datetime | None = Field(
        description="When the brand first opened the link; null until then"
    )
    ended_at: datetime | None = Field(
        description="When it was accepted, withdrawn, stopped or expired; null while it waits"
    )
    deal_memo_id: uuid.UUID | None = Field(
        description="The deal it became, once accepted; read it at /api/v1/deal-memos/{id}"
    )


class DirectOfferSent(DirectOfferRead):
    """A new offer, with its link's token: shown this once, never again."""

    link_token: str = Field(
        description=(
            "Put it in the link you send the brand, after a `#`, so no server ever "
            "receives it in a path. Shown only now; we keep only its keyed hash"
        )
    )


class OfferingCreator(BaseModel):
    """Who the offer is from: their public name, nothing else."""

    display_name: str
    handle: str


class DirectOfferLinkRead(DirectOfferTerms):
    """What the brand sees at the link: who it is from, and the terms."""

    creator: OfferingCreator
    brand_name: str = Field(
        description="The name the creator gave you; confirm or correct it"
    )
    expires_at: datetime
    notice: str = Field(
        description="What we do with the details given here, to show before accepting"
    )


class DirectOfferAcceptIn(BaseModel):
    """The brand's one step: its name, an email, the code, and the terms it saw."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    brand_name: BrandName
    email: BrandEmail
    date_of_birth: DateOfBirth
    code: OtpCode
    terms_sha256: TermsSha256


class DirectOfferAccepted(LoginTokens):
    """The brand is signed in to its new account, and the deal is agreed."""

    deal_memo_id: uuid.UUID
