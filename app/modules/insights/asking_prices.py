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

What each reader then does with the per-creator prices (a median, quartiles,
a floor of five) stays with that reader.
"""

from sqlalchemy import ColumnElement, Subquery, func, select

from app.core.taxonomy import CURRENCY
from app.modules.auth.models.creator import Creator
from app.modules.auth.suspension import account_is_active
from app.modules.profiles.models import CreatorPackage


def counted() -> list[ColumnElement[bool]]:
    """The conditions every counted package meets, on `CreatorPackage` joined
    to its `Creator`."""
    return [
        Creator.rate_card_public_at.is_not(None),
        account_is_active(Creator.account_id),
        CreatorPackage.currency == CURRENCY,
    ]


def per_creator(
    conditions: list[ColumnElement[bool]], *groups: ColumnElement[str]
) -> Subquery:
    """Each counted creator's own median price per platform and format, and
    per any further `groups` (a city, say), as `price`.

    `conditions` narrow the creators further (published Passports, a city);
    each of `groups` is labelled, and grouped on after the creator.
    """
    return (
        select(
            *groups,
            CreatorPackage.platform,
            CreatorPackage.format,
            func.percentile_cont(0.5)
            .within_group(CreatorPackage.price_paise)
            .label("price"),
        )
        .select_from(CreatorPackage)
        .join(Creator, Creator.id == CreatorPackage.creator_id)
        .where(*counted(), *conditions)
        .group_by(
            CreatorPackage.creator_id,
            *groups,
            CreatorPackage.platform,
            CreatorPackage.format,
        )
        .subquery()
    )
