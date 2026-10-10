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


def not_blocked_with_brand(one: AccountRef, brand_id: AccountRef) -> ColumnElement[bool]:
    """True unless `one` and the account behind a brand have blocked each other.

    The brand is joined inside the EXISTS, the way `suspension.brand_is_active`
    does it, so `Campaign.brand_id` correlates to the row being filtered. An
    earlier version wrapped the brand lookup in a scalar subquery nested in
    the EXISTS; SQLAlchemy did not correlate it, so it read every campaign's
    brand, and Postgres refused it as "more than one row" depending on the
    plan it chose. CI caught it on 10 October 2026, where the laptop did not.
    """
    return ~exists().where(
        Brand.id == brand_id,
        or_(
            and_(
                AccountBlock.blocker_account_id == one,
                AccountBlock.blocked_account_id == Brand.account_id,
            ),
            and_(
                AccountBlock.blocker_account_id == Brand.account_id,
                AccountBlock.blocked_account_id == one,
            ),
        ),
    )


def blocked_between(db: Session, one: uuid.UUID, other: uuid.UUID) -> bool:
    return not db.scalar(select(not_blocked(one, other)))
