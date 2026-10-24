"""Look-alike brand names: flags for creators, and the hold on publishing (item 75, D-118).

The rules are `brand_names`'. This reads what they need: the brands asked
about, and every brand here with a verified domain, whose names are
protected beside the curated list. One query for any number of brands.

The hold (option B): a brand whose name is flagged cannot publish a
campaign until it verifies the domain of the brand it resembles (item 74),
which the real brand does in minutes and an impersonator cannot.
"""

import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.auth.models.brand import Brand
from app.modules.profiles import brand_names
from app.modules.profiles.brand_domain_models import BrandDomain
from app.modules.profiles.brand_names import NameFlag
from app.modules.profiles.exceptions import BrandNameNeedsDomain


def flags_for(
    db: Session, brand_ids: Iterable[uuid.UUID], *, ignore_clearance: bool = False
) -> dict[uuid.UUID, NameFlag]:
    """Each flagged brand among `brand_ids`, with what its name resembles. One query.

    The one query reads the brands asked about and every brand with a
    verified domain, each with that domain, so a page of any length costs the
    same. A brand whose current name an admin cleared (D-119) is not flagged,
    unless `ignore_clearance`, which the admins' own review asks for.
    """
    wanted = set(brand_ids)
    if not wanted:
        return {}
    rows = (
        db.execute(
            select(Brand.id, Brand.name, Brand.name_cleared, BrandDomain.domain)
            .outerjoin(
                BrandDomain,
                (BrandDomain.brand_id == Brand.id) & (BrandDomain.status == "verified"),
            )
            .where(Brand.id.in_(wanted) | BrandDomain.id.is_not(None))
        )
        .tuples()
        .all()
    )
    names = {
        brand_id: name
        for brand_id, name, cleared, _ in rows
        if brand_id in wanted and (ignore_clearance or cleared != name)
    }
    verified = [(brand_id, name, domain) for brand_id, name, _, domain in rows if domain]
    own_domain = {brand_id: domain for brand_id, _, domain in verified}
    flags: dict[uuid.UUID, NameFlag] = {}
    for brand_id, name in names.items():
        protected = brand_names.protected_names(
            [
                (other, domain)
                for other_id, other, domain in verified
                if other_id != brand_id
            ]
        )
        flag = brand_names.flag_for(name, own_domain.get(brand_id), protected)
        if flag is not None:
            flags[brand_id] = flag
    return flags


@dataclass(frozen=True)
class FlaggedBrand:
    brand_id: uuid.UUID
    account_id: uuid.UUID
    name: str
    created_at: datetime
    flag: NameFlag


def flagged_brands(db: Session, limit: int) -> tuple[list[FlaggedBrand], bool]:
    """Every flagged brand, newest first, at most `limit`, and whether more exist.

    Reads every brand, as a pilot's few hundred allow (two queries); a
    scaling trigger in docs/ARCHITECTURE_SCALE.md says when to keep the flag
    instead.
    """
    brands = db.execute(
        select(Brand.id, Brand.account_id, Brand.name, Brand.created_at).order_by(
            Brand.created_at.desc(), Brand.id.desc()
        )
    ).all()
    flags = flags_for(db, [row.id for row in brands])
    found = [
        FlaggedBrand(row.id, row.account_id, row.name, row.created_at, flags[row.id])
        for row in brands
        if row.id in flags
    ]
    return found[:limit], len(found) > limit


def ensure_may_publish(db: Session, brand_id: uuid.UUID) -> None:
    """Refuse to publish under a flagged name. Raises BrandNameNeedsDomain."""
    flag = flags_for(db, [brand_id]).get(brand_id)
    if flag is None:
        return
    db.rollback()
    resembled = flag.resembles
    raise BrandNameNeedsDomain.for_name(
        None if resembled is None else resembled.name,
        None if resembled is None else resembled.domain,
        flag.mixed_script,
    )
