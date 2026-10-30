"""Which brand a request acts for, and in what role (item 13, D-148).

The one place brand access is decided (docs/PROPOSAL_TEAM_SEATS.md 4.3):

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
# The key, on a request's database session, of the account acting for the
# brand in that request: the deal record names it (D-148).
ACTING_ACCOUNT = "acting_brand_account_id"


@dataclass(frozen=True)
class BrandAccess:
    """A brand, and the role the asking account holds in it."""

    brand: Brand
    role: str


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
        select(Brand, BrandMember.role)
        .join(BrandMember, BrandMember.brand_id == Brand.id)
        .where(BrandMember.account_id == account.id, BrandMember.removed_at.is_(None))
        .order_by(BrandMember.created_at, BrandMember.id)
    ).all()
    if wanted is not None:
        found = next(((b, role) for b, role in rows if b.id == wanted), None)
        if found is None or not _owner_is_open(db, found[0]):
            raise BrandNotFound()
        return BrandAccess(found[0], found[1])
    if not rows:
        return None
    if len(rows) > 1:
        raise BrandChoiceNeeded()
    brand, role = rows[0]
    if not _owner_is_open(db, brand):
        raise BrandNotFound()
    return BrandAccess(brand, role)


def parse_brand_header(value: str | None) -> uuid.UUID | None:
    """The `Brand-Id` header as a UUID; a malformed one names no brand of anyone's."""
    if value is None or not value.strip():
        return None
    try:
        return uuid.UUID(value.strip())
    except ValueError as exc:
        raise BrandNotFound() from exc
