"""What "suspended" means, in one place, for every query that must respect it (D-061).

A suspended account is refused on every request, at login and on refresh.
A suspended creator leaves search, matching, the public Passport and the
fair-rate figures; a suspended brand's campaigns leave discovery and cannot
be applied to. **Existing deals are untouched**: the other party can still
read them, mark or confirm payment and open a dispute, so a suspension never
costs anyone the record of what they are owed.

Other modules filter through these helpers rather than rewriting the
condition, so every place agrees on who is suspended.
"""

import uuid

from sqlalchemy import ColumnElement, exists, select
from sqlalchemy.orm import InstrumentedAttribute, Session

from app.modules.auth.models.account import Account
from app.modules.auth.models.brand import Brand


def account_is_active(
    account_id: InstrumentedAttribute[uuid.UUID],
) -> ColumnElement[bool]:
    """True for rows whose account is not suspended."""
    return exists().where(Account.id == account_id, Account.suspended_at.is_(None))


def brand_is_active(brand_id: InstrumentedAttribute[uuid.UUID]) -> ColumnElement[bool]:
    """True for rows whose brand's account is not suspended."""
    return exists().where(
        Brand.id == brand_id,
        Account.id == Brand.account_id,
        Account.suspended_at.is_(None),
    )


def is_suspended(db: Session, account_id: uuid.UUID) -> bool:
    return (
        db.scalar(select(Account.suspended_at).where(Account.id == account_id))
        is not None
    )


def brand_is_suspended(db: Session, brand_id: uuid.UUID) -> bool:
    return (
        db.scalar(
            select(Account.suspended_at)
            .join(Brand, Brand.account_id == Account.id)
            .where(Brand.id == brand_id)
        )
        is not None
    )
