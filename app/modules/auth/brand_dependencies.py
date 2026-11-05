"""FastAPI dependencies for acting for a brand (item 13, D-148).

Here, in `auth`, so every module above it reaches a brand the same way: by
the `Brand-Id` header (`find_brand_access`), or through an object in the
path that names its brand (`acts_for_brand_of`). Either way the route's act
is checked (`auth.brand_acts`) and, on a write, who acts noted for the deal
record and the creator's notices. What "no brand at all" means is the
caller's to say: a campaign route answers 409, the brand's own profile 404.
"""

import uuid
from typing import Annotated

from fastapi import Depends, Header, Request
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.modules.auth import brand_access, brand_acts
from app.modules.auth.dependencies import CurrentAccount, CurrentBrand
from app.modules.auth.exceptions import BrandRoleNotAllowed
from app.modules.auth.models.account import Account

BrandIdHeader = Annotated[
    str | None,
    Header(
        alias=brand_access.BRAND_HEADER,
        description=(
            "The brand to act for, for someone in more than one (D-148). "
            "Leave it out to act for your own brand, or your only one."
        ),
    ),
]


def _allow(
    db: Session, request: Request, account: Account, access: brand_access.BrandAccess
) -> None:
    """Refuse a role this route's act is not given to; else, on a write, note who acts.

    403 `brand_role_not_allowed` when the role does not hold the act. Who
    acts goes on the request's own session (D-148), so an entry the deal
    record seals in this request names this person, and a creator told of it
    sees a member's first name. A read acts for nobody, so it notes nothing.
    """
    route = request.scope.get("route")
    path = getattr(route, "path", request.url.path)
    if not brand_acts.may(access.role, request.method, path):
        raise BrandRoleNotAllowed()
    if request.method not in ("GET", "HEAD"):
        brand_access.note_acting(
            db, brand_access.Acting(account.id, access.brand.id, access.member_id)
        )


def find_brand_access(
    request: Request,
    account: CurrentBrand,
    db: Annotated[Session, Depends(get_db)],
    brand_id: BrandIdHeader = None,
) -> brand_access.BrandAccess | None:
    """The brand the signed-in account acts for and its role, allowed this route.

    None when the account has no brand at all. 404 for a brand named but not
    theirs; 422 when it is in several and named none; 403 when their role
    does not hold this route's act. The owner passes every act check.
    """
    access = brand_access.resolve(db, account, brand_access.parse_brand_header(brand_id))
    if access is not None:
        _allow(db, request, account, access)
    return access


MaybeBrandAccess = Annotated[brand_access.BrandAccess | None, Depends(find_brand_access)]


def find_brand_access_of_any(
    request: Request,
    account: CurrentAccount,
    db: Annotated[Session, Depends(get_db)],
    brand_id: BrandIdHeader = None,
) -> brand_access.BrandAccess | None:
    """`find_brand_access` for a route both sides call (blocking): None for a
    creator, or a brand account in no brand, who act as themselves."""
    if account.role != "brand":
        return None
    return find_brand_access(request, account, db, brand_id)


AnyBrandAccess = Annotated[
    brand_access.BrandAccess | None, Depends(find_brand_access_of_any)
]


def acts_for_brand_of(
    db: Session, request: Request, account: Account, brand_id: uuid.UUID | None
) -> bool:
    """Whether a brand account may act for the brand an object names, on this route.

    For routes that reach a brand through the object in their path (a deal,
    an application), not the Brand-Id header: the owner or a live member of
    that brand. False when it is not theirs, for the caller's own 404, so
    membership is never revealed; 403 when their role does not hold the act.
    """
    access = brand_access.access_in(db, account, brand_id) if brand_id else None
    if access is None:
        return False
    _allow(db, request, account, access)
    return True
