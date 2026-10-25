"""What "suspended" and "deleted" mean, in one place, for every query that must respect them (D-061, D-122).

A suspended account is refused on every request, at login and on refresh.
A suspended creator leaves search, matching, the public Passport and the
fair-rate figures; a suspended brand's campaigns leave discovery and cannot
be applied to. **Existing deals are untouched**: the other party can still
read them, mark or confirm payment and open a dispute, so a suspension never
costs anyone the record of what they are owed.

A deleted account (item 6, D-122) is gone from all the same places, for
good, and nothing new can start with it; its deals stay readable by the
other side, as "a creator (or brand) who left". "Active" below means
neither suspended nor deleted; "unavailable" means either.

Other modules filter through these helpers rather than rewriting the
condition, so every place agrees on who is gone.
"""

import uuid

from sqlalchemy import ColumnElement, exists, select
from sqlalchemy.orm import InstrumentedAttribute, Session

from app.modules.auth.models.account import Account
from app.modules.auth.models.brand import Brand


def account_is_active(
    account_id: InstrumentedAttribute[uuid.UUID],
) -> ColumnElement[bool]:
    """True for rows whose account is neither suspended nor deleted."""
    return exists().where(
        Account.id == account_id,
        Account.suspended_at.is_(None),
        Account.deleted_at.is_(None),
    )


def brand_is_active(brand_id: InstrumentedAttribute[uuid.UUID]) -> ColumnElement[bool]:
    """True for rows whose brand's account is neither suspended nor deleted."""
    return exists().where(
        Brand.id == brand_id,
        Account.id == Brand.account_id,
        Account.suspended_at.is_(None),
        Account.deleted_at.is_(None),
    )


def is_unavailable(db: Session, account_id: uuid.UUID) -> bool:
    """True when the account is suspended or deleted."""
    return bool(
        db.scalar(
            select(
                (Account.suspended_at.is_not(None)) | (Account.deleted_at.is_not(None))
            ).where(Account.id == account_id)
        )
    )


def brand_is_unavailable(db: Session, brand_id: uuid.UUID) -> bool:
    """True when the brand's account is suspended or deleted."""
    return bool(
        db.scalar(
            select(
                (Account.suspended_at.is_not(None)) | (Account.deleted_at.is_not(None))
            )
            .join(Brand, Brand.account_id == Account.id)
            .where(Brand.id == brand_id)
        )
    )


def is_deleted(db: Session, account_id: uuid.UUID) -> bool:
    """True once the account is deleted (D-122). A suspension alone is not."""
    return (
        db.scalar(select(Account.deleted_at).where(Account.id == account_id)) is not None
    )
