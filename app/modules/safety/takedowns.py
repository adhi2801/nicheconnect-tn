"""Whether an item is withheld, for any query (item 52, D-104).

Used the way `suspension.py` and `blocks.py` are: as a condition inside the
query that picks rows, so a withheld item drops out in the same statement,
never by a query per row. Each condition is served by the partial unique
index `uq_takedown_active_subject`.

A campaign is withheld when it is, or when its brand is: an order against a
brand reaches everything it posts, including campaigns posted afterwards.
"""

import uuid
from typing import Any

from sqlalchemy import ColumnElement, and_, exists, select
from sqlalchemy.orm import InstrumentedAttribute, Session

from app.modules.safety.exceptions import ContentWithheld
from app.modules.safety.takedown_models import Takedown

ItemRef = uuid.UUID | ColumnElement[Any] | InstrumentedAttribute[uuid.UUID]


def not_withheld(subject_kind: str, subject_id: ItemRef) -> ColumnElement[bool]:
    """True unless this item has a takedown that has not been lifted."""
    return ~exists().where(
        Takedown.subject_kind == subject_kind,
        Takedown.subject_id == subject_id,
        Takedown.lifted_at.is_(None),
    )


def campaign_not_withheld(campaign_id: ItemRef, brand_id: ItemRef) -> ColumnElement[bool]:
    """True unless the campaign, or the brand behind it, is withheld."""
    return and_(not_withheld("campaign", campaign_id), not_withheld("brand", brand_id))


def is_withheld(db: Session, subject_kind: str, subject_id: uuid.UUID) -> bool:
    return not db.scalar(select(not_withheld(subject_kind, subject_id)))


def campaign_is_withheld(
    db: Session, campaign_id: uuid.UUID, brand_id: uuid.UUID
) -> bool:
    return not db.scalar(select(campaign_not_withheld(campaign_id, brand_id)))


def refuse_withheld_creator(db: Session, creator_id: uuid.UUID) -> None:
    """Raise ContentWithheld (451) if the creator's profile is withheld."""
    if is_withheld(db, "creator", creator_id):
        raise ContentWithheld()
