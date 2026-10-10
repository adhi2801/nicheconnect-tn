"""Whether two accounts have blocked each other, for any query (item 59).

Used the way `suspension.py` is: as a condition inside the query that picks
rows, so a blocked pair drops out in the same statement, never by a query
per row. A block works both ways: whoever placed it, neither side reaches
the other.
"""

import uuid
from typing import Any

from sqlalchemy import ColumnElement, and_, exists, or_, select
from sqlalchemy.orm import InstrumentedAttribute, Session

from app.modules.auth.models.block import AccountBlock
from app.modules.auth.models.brand import Brand

AccountRef = uuid.UUID | ColumnElement[Any] | InstrumentedAttribute[uuid.UUID]


def not_blocked(one: AccountRef, other: AccountRef) -> ColumnElement[bool]:
    """True unless either account has blocked the other."""
    return ~exists().where(
        or_(
            and_(
                AccountBlock.blocker_account_id == one,
                AccountBlock.blocked_account_id == other,
            ),
            and_(
                AccountBlock.blocker_account_id == other,
                AccountBlock.blocked_account_id == one,
            ),
        )
    )


def brand_account(brand_id: AccountRef) -> ColumnElement[Any]:
    """The account behind a brand, as an expression for the conditions above."""
    return select(Brand.account_id).where(Brand.id == brand_id).scalar_subquery()


def blocked_between(db: Session, one: uuid.UUID, other: uuid.UUID) -> bool:
    return not db.scalar(select(not_blocked(one, other)))
