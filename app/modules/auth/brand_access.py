"""Which brand a request acts for, and in what role (item 13, D-148).

The one place brand access is decided (docs/decided/PROPOSAL_TEAM_SEATS.md 4.3):

- the owner is `brand.account_id`; everyone else holds a live `brand_member`
  row with a role;
- the brand travels in the `Brand-Id` header, the pattern of Stripe's
  `Stripe-Account`. Without it: the account's own brand, else its only
  membership, else 422 `brand_choice_needed`;
- a brand the account neither owns nor belongs to is 404, never 403, so
  membership is never revealed;
- a brand whose owner is suspended or has left is closed to its members
  too: a member cannot keep a suspended business running.

What each role may then do is `auth.brand_acts`.
"""

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.auth.exceptions import BrandChoiceNeeded, BrandNotFound
from app.modules.auth.models.account import Account
from app.modules.auth.models.brand import Brand
from app.modules.auth.models.brand_team import BrandMember

BRAND_HEADER = "Brand-Id"
# The key, on a request's database session, of who acts for a brand in that
# request (D-148): the deal record seals the account, and a creator told of a
# member's act is shown the member's first name.
_ACTING = "acting_for_brand"


@dataclass(frozen=True)
class BrandAccess:
    """A brand, the role the asking account holds in it, and, for a member,
    their membership (None for the owner)."""

    brand: Brand
    role: str
    member_id: uuid.UUID | None = None


@dataclass(frozen=True)
class Acting:
    """Who changes something for a brand in this request (D-148)."""

    account_id: uuid.UUID
    brand_id: uuid.UUID
    # None when the owner acts: the brand's own name stands for them. The
    # membership, never a copy of the name, so erasing it erases the name.
    member_id: uuid.UUID | None


def note_acting(db: Session, acting: Acting) -> None:
    """Note on the request's session who acts for the brand in it."""
    db.info[_ACTING] = acting


def acting(db: Session) -> Acting | None:
    """Who acts for a brand in this request, or None (a creator, a job, a read)."""
    found = db.info.get(_ACTING)
    return found if isinstance(found, Acting) else None


def forget_acting(db: Session) -> None:
    """Start a request knowing nobody acts yet.

    Called as each request authenticates: a session can outlive a request
    (the tests share one), and a note left by one request must never name
    its account on another's act.
    """
    db.info.pop(_ACTING, None)


def _owner_is_open(db: Session, brand: Brand) -> bool:
    """Whether the brand's owner still stands: not suspended, not left."""
    owner = db.get(Account, brand.account_id)
    return owner is not None and owner.suspended_at is None and owner.deleted_at is None


def resolve(
    db: Session, account: Account, wanted: uuid.UUID | None
) -> BrandAccess | None:
    """The brand `account` acts for, or None when it has none at all.

    Raises BrandNotFound for a brand named but not theirs (or closed with its
    owner), BrandChoiceNeeded when several are theirs and none is named.
    Two queries at most: the owned brand, then the memberships.
    """
    own = db.scalars(select(Brand).where(Brand.account_id == account.id)).first()
    if wanted is None and own is not None:
        return BrandAccess(own, "owner")
    if own is not None and own.id == wanted:
        return BrandAccess(own, "owner")
    rows = db.execute(
        select(Brand, BrandMember.role, BrandMember.id)
        .join(BrandMember, BrandMember.brand_id == Brand.id)
        .where(BrandMember.account_id == account.id, BrandMember.removed_at.is_(None))
        .order_by(BrandMember.created_at, BrandMember.id)
    ).all()
    if wanted is not None:
        found = next((row for row in rows if row[0].id == wanted), None)
        if found is None or not _owner_is_open(db, found[0]):
            raise BrandNotFound()
        return BrandAccess(found[0], found[1], found[2])
    if not rows:
        return None
    if len(rows) > 1:
        raise BrandChoiceNeeded()
    brand, role, member_id = rows[0]
    if not _owner_is_open(db, brand):
        raise BrandNotFound()
    return BrandAccess(brand, role, member_id)


def parse_brand_header(value: str | None) -> uuid.UUID | None:
    """The `Brand-Id` header as a UUID; a malformed one names no brand of anyone's."""
    if value is None or not value.strip():
        return None
    try:
        return uuid.UUID(value.strip())
    except ValueError as exc:
        raise BrandNotFound() from exc


def access_in(db: Session, account: Account, brand_id: uuid.UUID) -> BrandAccess | None:
    """The account's access to a brand named by an object (a deal, an
    application), or None when it is not theirs, or its owner is suspended or
    has left.

    For routes that reach a brand through the object they name, not the
    Brand-Id header: the object says which brand. Two queries at most.
    """
    brand = db.get(Brand, brand_id)
    if brand is None:
        return None
    if brand.account_id == account.id:
        return BrandAccess(brand, "owner")
    row = db.execute(
        select(BrandMember.role, BrandMember.id).where(
            BrandMember.brand_id == brand_id,
            BrandMember.account_id == account.id,
            BrandMember.removed_at.is_(None),
        )
    ).first()
    if row is None or not _owner_is_open(db, brand):
        return None
    return BrandAccess(brand, row[0], row[1])


def role_in(db: Session, account: Account, brand_id: uuid.UUID) -> str | None:
    """The account's role in a brand named by an object, or None (`access_in`)."""
    found = access_in(db, account, brand_id)
    return found.role if found is not None else None
