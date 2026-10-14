"""Request and response shapes for city figures and fair-rate guidance (D-099)."""

from datetime import date
from typing import Literal

from pydantic import (
    BaseModel,
    Field,
)

from app.core.taxonomy import CURRENCY, Niche
from app.modules.auth.schemas import ChannelPlatform, PackageFormat

AudienceBand = Literal["under_10k", "10k_50k", "50k_100k", "100k_500k", "500k_plus"]


class NarrowedTo(BaseModel):
    """Which filters the figures actually used. Null means "all of them"."""

    niche: Niche | None
    city: str | None


class RateGuidanceRead(BaseModel):
    """What creators like this charge: a range, never a verdict.

    **Null figures mean "not enough to say"**, fewer than five creators, and
    must never be shown as zero. There is deliberately no minimum or maximum:
    each would be one person's price.
    """

    platform: ChannelPlatform
    format: PackageFormat
    audience_band: AudienceBand
    narrowed_to: NarrowedTo = Field(
        description=(
            "The niche and city the figures are for. If one you asked for is "
            "null here, there were too few creators with it and the answer "
            "is wider"
        )
    )
    source: Literal["published_asking_prices"] = Field(
        description="Prices creators ask and have chosen to publish, not agreed fees"
    )
    creators_counted: int = Field(
        description="Creators behind the figures, each counted once"
    )
    lower_quarter_paise: int | None
    median_paise: int | None
    upper_quarter_paise: int | None
    currency: str
    audience_self_reported: Literal[True] = Field(
        default=True,
        description="Bands come from follower counts creators stated; we never checked",
    )
    audience_figures_from: date | None = Field(
        description="Date of the oldest follower count behind the figures"
    )
    as_of: date = Field(description="The day these figures were worked out")


class CityCountRead(BaseModel):
    city: str = Field(description="As most of its creators spell it")
    published_creators: int


class AskingPriceRead(BaseModel):
    """The median asking price for one platform and format in a city.

    Each creator counts once; only groups of five creators or more appear.
    """

    platform: ChannelPlatform
    format: PackageFormat
    creators: int
    median_paise: int
    currency: str = CURRENCY


class NicheCountRead(BaseModel):
    niche: Niche
    creators: int | None = Field(description="Null below five: not enough to say")


class CityFiguresRead(BaseModel):
    """One city's public figures: counts and medians, five or nothing.

    Every count rests on creators who published their Passport, or on open
    campaigns; nothing comes from a deal. **Null means "not enough to say"
    and must never be shown as zero.**
    """

    city: str
    min_count: int = Field(description="The smallest count any figure is shown for")
    published_creators: int | None
    creators_by_niche: list[NicheCountRead]
    open_campaigns: int | None
    asking_prices: list[AskingPriceRead]
