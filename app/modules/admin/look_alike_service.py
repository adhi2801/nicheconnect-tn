"""Brands whose names look like a protected brand's, for the admins (item 75, D-118).

The rules are `profiles.brand_name_service`'s; this only hands the admin
side what it needs.
"""

from sqlalchemy.orm import Session

from app.modules.profiles import brand_name_service
from app.modules.profiles.brand_name_service import FlaggedBrand

MAX_LISTED = 100


def flagged(db: Session) -> tuple[list[FlaggedBrand], bool]:
    """The newest flagged brands, at most MAX_LISTED, and whether more exist."""
    return brand_name_service.flagged_brands(db, MAX_LISTED)
