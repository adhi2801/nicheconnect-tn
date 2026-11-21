"""Which asking prices count, written once (D-056, D-078; item 84, D-200).

City figures, fair-rate guidance and the quarterly rate report all report
what creators ask. Until item 84 the rule was written twice; it is here once,
so the three can never drift apart:

- **Only published rate cards count.** Those creators chose to show their
  prices to strangers (D-056).
- **Suspended accounts never count** (D-061): a fake profile's numbers must
  not shape what others are told is usual.
- **Rupees only** (D-015).
- **Each creator counts once:** their packages in a group are reduced to
  their own median first, so one creator with five Reel packages cannot
  outweigh four others.

- **An audience band is the creator's own channel on the package's
  platform** (D-056): its stated followers decide the band, and the oldest
  date behind those figures is carried as `figures_as_of`. Fair-rate
  guidance and the rate report's statewide bands both count by it.

What each reader then does with the per-creator prices (a median, quartiles,
a floor of five) stays with that reader.
"""

from collections.abc import Sequence
from typing import Any

from sqlalchemy import ColumnElement, Subquery, and_, case, func, select, true

from app.core.taxonomy import CURRENCY
from app.modules.auth.models.creator import Creator
from app.modules.auth.suspension import account_is_active
from app.modules.profiles.models import CreatorChannel, CreatorPackage


def counted() -> list[ColumnElement[bool]]:
    """The conditions every counted package meets, on `CreatorPackage` joined
    to its `Creator`."""
    return [
        Creator.rate_card_public_at.is_not(None),
        account_is_active(Creator.account_id),
        CreatorPackage.currency == CURRENCY,
    ]


def in_band(low: int, high: int | None) -> ColumnElement[bool]:
    """The creator's own channel's followers are in [low, high); no `high`
    is no upper end. Meant for `per_creator(..., by_audience=True)`."""
    followers = CreatorChannel.followers
    return and_(followers >= low, followers < high if high is not None else true())


def band_of(bands: Sequence[tuple[str, int, int | None]]) -> ColumnElement[Any]:
    """Which of `bands` (label, low, high) the creator's own channel is in."""
    return case(*[(in_band(low, high), label) for label, low, high in bands])


def per_creator(
    conditions: list[ColumnElement[bool]],
    *groups: ColumnElement[Any],
    by_audience: bool = False,
) -> Subquery:
    """Each counted creator's own median price per platform and format, and
    per any further `groups` (a city, say), as `price`.

    `conditions` narrow the creators further (published Passports, a city);
    each of `groups` is labelled, and grouped on after the creator.

    `by_audience` joins the creator's own channel on the package's platform,
    so `in_band` and `band_of` can be used in `conditions` and `groups`, and
    adds `figures_as_of`, the oldest date behind its follower count. A
    creator with no channel on that platform has no band, and is left out.
    """
    figures: list[ColumnElement[Any]] = (
        [func.min(CreatorChannel.figures_as_of).label("figures_as_of")]
        if by_audience
        else []
    )
    query = (
        select(
            *groups,
            CreatorPackage.platform,
            CreatorPackage.format,
            func.percentile_cont(0.5)
            .within_group(CreatorPackage.price_paise)
            .label("price"),
            *figures,
        )
        .select_from(CreatorPackage)
        .join(Creator, Creator.id == CreatorPackage.creator_id)
    )
    if by_audience:
        query = query.join(
            CreatorChannel,
            and_(
                CreatorChannel.creator_id == CreatorPackage.creator_id,
                CreatorChannel.platform == CreatorPackage.platform,
            ),
        )
    return (
        query.where(*counted(), *conditions)
        .group_by(
            CreatorPackage.creator_id,
            *groups,
            CreatorPackage.platform,
            CreatorPackage.format,
        )
        .subquery()
    )
