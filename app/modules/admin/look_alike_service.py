"""Brands whose names look like a protected brand's, for the admins (items 75, D-118, D-119).

The rules are `profiles.brand_name_service`'s. This adds what only an admin
does: listing them, and clearing a name after looking at the brand behind
it, so a genuine shop with a close name and no website can publish. A
clearance is of the exact name, so a rename is looked at afresh, and it can
be withdrawn. Both go in the admin log with the admin's note.
"""

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.admin.admin_service import log_action
from app.modules.admin.exceptions import (
    BrandNameAlreadyCleared,
    BrandNameNotCleared,
    BrandNameNotFlagged,
)
from app.modules.auth.exceptions import AdminNotFound
from app.modules.auth.models.account import Account
from app.modules.auth.models.brand import Brand
from app.modules.profiles import brand_name_service
from app.modules.profiles.brand_name_service import FlaggedBrand

MAX_LISTED = 100


def flagged(db: Session) -> tuple[list[FlaggedBrand], bool]:
    """The newest held brands, at most MAX_LISTED, and whether more exist."""
    return brand_name_service.flagged_brands(db, MAX_LISTED)


def _locked_brand(db: Session, brand_id: uuid.UUID) -> Brand:
    brand = db.scalars(
        select(Brand).where(Brand.id == brand_id).with_for_update()
    ).first()
    if brand is None:
        db.rollback()
        raise AdminNotFound("No such brand.")
    return brand


def clear_name(
    db: Session, admin: Account, brand_id: uuid.UUID, *, note: str, now: datetime
) -> Brand:
    """Clear the brand's current name, after an admin looked at it. Commits.

    Locked first, so a rename at the same moment is either cleared or not,
    never half. Raises AdminNotFound, BrandNameAlreadyCleared and
    BrandNameNotFlagged.
    """
    brand = _locked_brand(db, brand_id)
    if brand.name_cleared == brand.name:
        db.rollback()
        raise BrandNameAlreadyCleared()
    if brand.id not in brand_name_service.flags_for(
        db, [brand.id], ignore_clearance=True
    ):
        db.rollback()
        raise BrandNameNotFlagged()
    brand.name_cleared = brand.name
    brand.name_cleared_at = now
    brand.name_cleared_by_account_id = admin.id
    brand.updated_at = now
    log_action(
        db, admin, "clear_brand_name", now, subject_account_id=brand.account_id, note=note
    )
    db.commit()
    return brand


def withdraw_clearance(
    db: Session, admin: Account, brand_id: uuid.UUID, *, note: str, now: datetime
) -> Brand:
    """Withdraw the clearance of the brand's current name. Commits.

    Raises AdminNotFound and BrandNameNotCleared.
    """
    brand = _locked_brand(db, brand_id)
    if brand.name_cleared is None or brand.name_cleared != brand.name:
        db.rollback()
        raise BrandNameNotCleared()
    brand.name_cleared = None
    brand.name_cleared_at = None
    brand.name_cleared_by_account_id = None
    brand.updated_at = now
    log_action(
        db,
        admin,
        "withdraw_brand_name_clearance",
        now,
        subject_account_id=brand.account_id,
        note=note,
    )
    db.commit()
    return brand
