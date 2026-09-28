"""What creators like this one charge: fair-rate guidance, step 1 (D-056).

A range, never a verdict. It answers "what do creators of this size charge for
this format on this platform?", narrowed to a niche and a city when there is
enough data, and always says how many creators it came from.

The rules, each for a reason:

- **Only published rate cards count.** Those creators chose to show their
  prices to strangers, so counting them anonymously needs no new consent.
  Whether every creator's prices may be counted is a DPDP question for the
  validation pack (constraint 6), not ours to guess.
- **Each creator counts once.** Their packages in a group are reduced to their
  own median first, so one creator with five Reel packages cannot outweigh
  four others.
- **Quartiles only, never a minimum or maximum**: each of those is one
  person's price.
- **Five creators or nothing.** Below that the figures are None, meaning *not
  enough to say*, as in the delivery record (D-038). Never zero, never an
  estimate.
- **Narrowing is reported, never silent.** Niche and city, then niche alone,
  then neither; the answer says which it used.
"""

from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy import ColumnElement, and_, func, select, true
from sqlalchemy.orm import Session

from app.core.taxonomy import CURRENCY, Niche
from app.modules.auth.models.creator import Creator
from app.modules.auth.models.rate_card import CreatorChannel, CreatorPackage
from app.modules.auth.schemas import AudienceBand

MIN_CREATORS = 5

# (label, lowest follower count, first count above the band). Tamil Nadu's
# pilot creators are mostly micro, so 10k to 100k is split in two.
AUDIENCE_BANDS: tuple[tuple[AudienceBand, int, int | None], ...] = (
    ("under_10k", 0, 10_000),
    ("10k_50k", 10_000, 50_000),
    ("50k_100k", 50_000, 100_000),
    ("100k_500k", 100_000, 500_000),
    ("500k_plus", 500_000, None),
)


def audience_band(followers: int) -> tuple[AudienceBand, int, int | None]:
    for band in AUDIENCE_BANDS:
        _, low, high = band
        if followers >= low and (high is None or followers < high):
            return band
    raise ValueError(f"No band for {followers} followers")  # followers < 0


@dataclass(frozen=True)
class Guidance:
    audience_band: AudienceBand
    niche: Niche | None
    city: str | None
    creators_counted: int
    lower_quarter_paise: int | None
    median_paise: int | None
    upper_quarter_paise: int | None
    audience_figures_from: date | None


def _levels(
    niche: Niche | None, city: str | None
) -> list[tuple[Niche | None, str | None]]:
    """Narrowest first, each step dropping one filter. No step repeats."""
    levels: list[tuple[Niche | None, str | None]] = []
    for level in ((niche, city), (niche, None), (None, None)):
        if level not in levels:
            levels.append(level)
    return levels


def for_group(
    db: Session,
    *,
    platform: str,
    package_format: str,
    followers: int,
    niche: Niche | None,
    city: str | None,
) -> Guidance:
    """The range for this group, in one query whatever the narrowing."""
    band, low, high = audience_band(followers)
    city = city.strip() if city else None

    per_creator = (
        select(
            CreatorPackage.creator_id,
            func.percentile_cont(0.5)
            .within_group(CreatorPackage.price_paise)
            .label("price"),
            (Creator.niches.any_() == niche if niche else true()).label("in_niche"),
            # Cities are typed by people, so "madurai" finds "Madurai".
            (func.lower(Creator.city) == city.lower() if city else true()).label(
                "in_city"
            ),
            func.min(CreatorChannel.figures_as_of).label("figures_as_of"),
        )
        .join(Creator, Creator.id == CreatorPackage.creator_id)
        .join(
            CreatorChannel,
            and_(
                CreatorChannel.creator_id == CreatorPackage.creator_id,
                CreatorChannel.platform == CreatorPackage.platform,
            ),
        )
        .where(
            CreatorPackage.platform == platform,
            CreatorPackage.format == package_format,
            CreatorPackage.currency == CURRENCY,
            Creator.rate_card_public_at.is_not(None),
            CreatorChannel.followers >= low,
            CreatorChannel.followers < high if high is not None else true(),
        )
        .group_by(CreatorPackage.creator_id, Creator.niches, Creator.city)
        .subquery()
    )

    levels = _levels(niche, city)
    columns: list[ColumnElement[Any]] = []
    for level_niche, level_city in levels:
        condition = and_(
            per_creator.c.in_niche if level_niche else true(),
            per_creator.c.in_city if level_city else true(),
        )
        columns += [
            func.count().filter(condition),
            func.percentile_cont(0.25)
            .within_group(per_creator.c.price)
            .filter(condition),
            func.percentile_cont(0.5).within_group(per_creator.c.price).filter(condition),
            func.percentile_cont(0.75)
            .within_group(per_creator.c.price)
            .filter(condition),
            func.min(per_creator.c.figures_as_of).filter(condition),
        ]
    row = db.execute(select(*columns).select_from(per_creator)).one()

    for index, (level_niche, level_city) in enumerate(levels):
        count, lower, median, upper, figures_from = row[index * 5 : index * 5 + 5]
        if count >= MIN_CREATORS:
            return Guidance(
                audience_band=band,
                niche=level_niche,
                city=level_city,
                creators_counted=count,
                lower_quarter_paise=round(lower),
                median_paise=round(median),
                upper_quarter_paise=round(upper),
                audience_figures_from=figures_from,
            )

    # Not enough anywhere: say how many there were at the widest level, and
    # nothing else.
    widest_count = row[(len(levels) - 1) * 5]
    return Guidance(
        audience_band=band,
        niche=None,
        city=None,
        creators_counted=widest_count,
        lower_quarter_paise=None,
        median_paise=None,
        upper_quarter_paise=None,
        audience_figures_from=None,
    )
