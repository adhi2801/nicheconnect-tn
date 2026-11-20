"""The quarterly city rate report's shapes (item 84, D-200).

`RateReportBody` is both what is stored and what is answered: the stored
JSON is this model's dump, so a reader gets exactly what was fingerprinted.
Response fields are additive only (backend.md section 2); a new kind of
cell comes with a new `method_version`.

**Null means "not enough to say"** everywhere a figure or a count can be
null, and must never be drawn as zero.
"""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.core.taxonomy import CURRENCY
from app.modules.auth.schemas import ChannelPlatform, PackageFormat
from app.modules.insights.schemas import AudienceBand

NULL_MEANS = "Null below the floor in `min_counts`: not enough to say, never zero"


class AskingCellRead(BaseModel):
    """What creators ask, for one platform and format: published rate cards."""

    platform: ChannelPlatform
    format: PackageFormat
    creators: int | None = Field(
        description="Creators behind the figures, each counted once. " + NULL_MEANS
    )
    lower_quarter_paise: int | None = Field(description=NULL_MEANS)
    median_paise: int | None = Field(description=NULL_MEANS)
    upper_quarter_paise: int | None = Field(description=NULL_MEANS)


class AgreedCellRead(BaseModel):
    """What was agreed, for one platform and format: accepted memos with one
    deliverable, each creator's own median first."""

    platform: ChannelPlatform
    format: PackageFormat
    deals: int | None = Field(
        description="Deals in the cell, barter included. " + NULL_MEANS
    )
    creators: int | None = Field(description=NULL_MEANS)
    brands: int | None = Field(description=NULL_MEANS)
    barter_share_percent: int | None = Field(
        description="The share of the cell's deals paid in goods, not money. "
        + NULL_MEANS
    )
    lower_quarter_paise: int | None = Field(
        description="Only once the paid deals rest on 10 creators or more. " + NULL_MEANS
    )
    median_paise: int | None = Field(description=NULL_MEANS)
    upper_quarter_paise: int | None = Field(
        description="Only once the paid deals rest on 10 creators or more. " + NULL_MEANS
    )


class CityRatesRead(BaseModel):
    city: str = Field(description="As most of its creators spell it")
    asking_prices: list[AskingCellRead] = Field(
        description="Every platform and format, in a fixed order, null where too few"
    )
    agreed_fees: list[AgreedCellRead] | None = Field(
        description="Null when this report was built without agreed fees"
    )


class AudienceBandCellRead(BaseModel):
    """Statewide asking prices for one audience band, platform and format."""

    audience_band: AudienceBand
    platform: ChannelPlatform
    format: PackageFormat
    creators: int | None = Field(description=NULL_MEANS)
    lower_quarter_paise: int | None = Field(description=NULL_MEANS)
    median_paise: int | None = Field(description=NULL_MEANS)
    upper_quarter_paise: int | None = Field(description=NULL_MEANS)
    audience_figures_from: date | None = Field(
        description=(
            "The oldest follower count behind the band, as creators stated it; "
            "we never checked it"
        )
    )


class MinCountsRead(BaseModel):
    """The floors this report was built with (docs/RATE_REPORT_METHOD.md)."""

    asking_creators: int
    agreed_deals: int
    agreed_creators: int
    agreed_brands: int
    agreed_max_brand_share_percent: int
    agreed_quartiles_creators: int
    rounded_to_paise: int = Field(description="Every figure to the nearest of these")


class RateReportBody(BaseModel):
    """One quarter's figures, aggregate numbers only: no id, handle or name."""

    model_config = ConfigDict(extra="forbid")

    quarter: str = Field(examples=["2026-Q4"])
    method_version: int
    period_from: date = Field(description="The quarter's first day, in Tamil Nadu")
    period_to: date = Field(description="The quarter's last day, in Tamil Nadu")
    as_of: date = Field(
        description=(
            "The day the figures were worked out. Asking prices are the published "
            "rate cards on that day; agreed fees, the memos accepted in the quarter"
        )
    )
    currency: Literal["INR"] = CURRENCY
    min_counts: MinCountsRead
    agreed_fees_included: bool = Field(
        description="False while agreed fees are switched off; then every city's is null"
    )
    cities: list[CityRatesRead] = Field(
        description="Cities with at least five published creators, largest first"
    )
    audience_bands: list[AudienceBandCellRead] = Field(
        description="Statewide asking prices by follower band, platform and format"
    )


class RateReportRead(BaseModel):
    """A published quarterly report. Never changes once published."""

    quarter: str = Field(examples=["2026-Q4"])
    method_version: int
    method_url: str = Field(description="The rules this report was built by, in words")
    built_at: datetime
    published_at: datetime
    body_sha256: str = Field(
        description=(
            "SHA-256 of `body` as canonical JSON (keys sorted, no spaces, UTF-8), "
            "so any copy can be checked against this one"
        )
    )
    body: RateReportBody


class RateReportSummaryRead(BaseModel):
    """One published quarter, for the archive."""

    quarter: str = Field(examples=["2026-Q4"])
    method_version: int
    published_at: datetime
    withdrawn_at: datetime | None = Field(
        description="Set when it was withdrawn; reading it then answers 410 with why"
    )
    body_sha256: str


class WithdrawRateReportIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    reason: str = Field(
        min_length=10,
        max_length=500,
        description="Why, shown to every reader of the withdrawn report",
    )


class AdminRateReportRead(BaseModel):
    """A report's state as an admin sees it after publishing or withdrawing."""

    quarter: str
    method_version: int
    built_at: datetime
    published_at: datetime | None
    withdrawn_at: datetime | None
    withdrawn_reason: str | None
    body_sha256: str
