"""The campaign report's shape (item 47, D-088). Built in `report_service`."""

import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.core.taxonomy import CURRENCY
from app.modules.campaigns.schemas import (
    ApplicationCountsRead,
    CampaignStatus,
    CampaignType,
)
from app.modules.deal_memo.schemas import DealSide, DealStageName
from app.modules.payment_status.schemas import PaymentState


class ReportNumbersRead(BaseModel):
    """Each figure summed over the counted readings; null when none showed it."""

    views: int | None
    reach: int | None
    impressions: int | None
    likes: int | None
    comments: int | None
    saves: int | None
    shares: int | None


class ReportResultsRead(BaseModel):
    """What the approved work's screenshots said (D-070).

    **Read from screenshots, never verified**: a screenshot can be edited.
    Readings the creator marked as wrong are counted apart and left out of
    the numbers.
    """

    source: Literal["read_from_screenshots"] = "read_from_screenshots"
    readings: int = Field(description="Screenshots read and counted in the numbers")
    readings_marked_wrong: int = Field(
        description="Readings the creator said are wrong: left out of the numbers"
    )
    includes_abbreviated: bool = Field(
        description="A figure was shown abbreviated on screen (such as 12.5K), "
        "so a sum is not exact"
    )
    numbers: ReportNumbersRead


class ReportSealRead(BaseModel):
    """The deal record behind this line (D-057, D-060)."""

    intact: bool = Field(description="Every entry's seal checks against the one before")
    entries: int
    latest_seal: str | None = Field(
        description="SHA-256 of the record's latest entry, as hex. Keep it to catch "
        "a rewrite later; `GET /api/v1/deal-memos/{id}/record` shows every entry",
        examples=["5f1c0b9e4a7d2c3b8e6f0a1d2c3b4a5f6e7d8c9b0a1f2e3d4c5b6a7f8e9d0c1b"],
    )
    stamped_on: date | None = Field(
        description="The first daily checkpoint holding the latest seal that an "
        "outside timestamp authority signed, as a Tamil Nadu date. Null until "
        "the next one. `GET /api/v1/deal-memos/{id}/record/proof` gives the "
        "proof that checks it"
    )


class ReportCreatorRead(BaseModel):
    """The creator as the brand already sees them; nothing private."""

    display_name: str
    handle: str


class ReportDealRead(BaseModel):
    deal_memo_id: uuid.UUID
    creator: ReportCreatorRead
    stage: DealStageName = Field(
        description="Where the deal stands as of the report (D-076). Clients "
        "ignore values they do not know"
    )
    waiting_on: DealSide | None
    has_open_dispute: bool
    deliverables: str
    content_due_on: date | None = Field(description="The date agreed in the memo")
    work_due_on: date | None = Field(
        description="The date the work is due by: the agreed date, moved a day for "
        "every whole day a draft waited for the brand (D-140). On-time is judged "
        "against this"
    )
    fee_amount_paise: int | None = Field(description="Null for a barter deal")
    currency: Literal["INR"] = CURRENCY
    accepted_on: date | None
    first_submitted_on: date | None = Field(
        description="When the creator first sent work, in Tamil Nadu"
    )
    delivered_on_time: bool | None = Field(
        description="First sent on or before the agreed date. Null with no work "
        "sent yet, or no date agreed"
    )
    approved_on: date | None = Field(
        description="When the work was approved; by the clock, the day its "
        "review window ended (D-025)"
    )
    approved_by_clock: bool
    content_url: str | None = Field(description="The approved post's link")
    disclosure_confirmed: bool | None = Field(
        description="The creator's own confirmation that the post carries the ad "
        "label, as recorded (D-024). Null until work is approved"
    )
    payment_state: PaymentState | None = Field(
        description="Null until the work is approved and a payment is due. "
        "Clients ignore values they do not know"
    )
    payment_due_on: date | None
    payment_marked_paid_on: date | None = Field(
        description="When the brand said it sent the money"
    )
    payment_confirmed_on: date | None = Field(
        description="When the creator confirmed it arrived"
    )
    paid_on_time: bool | None = Field(
        description="Marked as sent on or before the due date. Null until marked"
    )
    results: ReportResultsRead
    record: ReportSealRead


class ReportTotalsRead(BaseModel):
    applications: ApplicationCountsRead
    deals: int = Field(description="Memos sent, in any stage; drafts are left out")
    deals_agreed: int = Field(description="Agreed and not cancelled")
    deals_finished: int
    barter_deals_agreed: int
    currency: Literal["INR"] = CURRENCY
    agreed_value_paise: int = Field(description="Fees of the agreed deals")
    marked_paid_paise: int = Field(description="Said by the brand to be sent")
    confirmed_paise: int = Field(description="Confirmed by the creator as arrived")
    deliveries_judged: int = Field(
        description="Deals with an agreed date whose work was sent"
    )
    delivered_on_time: int
    payments_sent: int = Field(description="Payments the brand marked as sent")
    payments_sent_on_time: int
    results: ReportResultsRead
    records_intact: bool = Field(description="Every deal's record checks")


class CampaignReportRead(BaseModel):
    """Every deal on one campaign, with the proof behind it (item 47).

    Worked out from the records as of `generated_at`, never stored. Dates are
    Tamil Nadu dates. The same report as a spreadsheet is
    `GET /api/v1/campaigns/{id}/report.csv`.
    """

    campaign_id: uuid.UUID
    title: str
    status: CampaignStatus
    campaign_type: CampaignType
    generated_at: datetime
    totals: ReportTotalsRead
    deals: list[ReportDealRead]
