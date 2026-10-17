"""A brand's domain: claiming it, checking it, and showing it (item 74, D-106).

The rules are `brand_domains.py`'s; the lookups `domain_lookup.py`'s. Here
they meet the database:

- **claim** and **withdraw** are the brand's own, one claim per brand
  (`INSERT ... ON CONFLICT`); a new claim always gets a new token;
- **request_check** only marks the claim: a request never waits on DNS
  (CLAUDE.md section 3). The checking job runs every minute;
- **the job** takes due claims under SKIP LOCKED with a lease, looks them up
  with no transaction open, then applies each result under the claim's row
  lock, only if the claim still has the token that was looked up;
- **verified_for_brands** gives creators the facts, one query for a page.

One verified holder per domain, held by the database's partial unique
index; a second brand that proves the same domain is told it is held.
"""

import logging
import uuid
from collections.abc import Callable, Iterable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlalchemy import and_, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.export import ExportedSection, allow, build_section
from app.modules.auth.models.brand import Brand
from app.modules.profiles import brand_domains as rules
from app.modules.profiles.brand_domain_models import BrandDomain
from app.modules.profiles.domain_lookup import DomainLookup
from app.modules.profiles.exceptions import (
    DomainClaimExpired,
    DomainClaimLapsed,
    DomainClaimNotFound,
    DomainHeldElsewhere,
    DomainNotAcceptable,
)

logger = logging.getLogger(__name__)

# Claims one run takes; the rest wait a minute for the next.
BATCH_SIZE = 20
# A run that died leaves its claims taken; after this, another run retakes them.
LEASE = timedelta(minutes=5)
UNIQUE_VERIFIED = "uq_brand_domain_verified_domain"


def claim(db: Session, brand: Brand, typed_domain: str, now: datetime) -> BrandDomain:
    """Claim a domain, replacing any earlier claim, with a new token.

    Raises DomainNotAcceptable (with what to claim instead) and
    DomainHeldElsewhere.
    """
    try:
        domain = rules.registrable_domain(typed_domain)
    except rules.DomainNotAccepted as refused:
        raise DomainNotAcceptable(str(refused)) from None
    if _held_by_another(db, domain, brand.id):
        db.rollback()
        raise DomainHeldElsewhere()
    fresh = {
        "domain": domain,
        "token": rules.new_token(),
        "status": "pending",
        "claimed_at": now,
        "token_expires_at": now + rules.TOKEN_LIFETIME,
        "check_requested_at": None,
        "checking_since": None,
        "last_checked_at": None,
        "last_result": None,
        "consecutive_absent": 0,
        "verified_at": None,
        "lapsed_at": None,
        "dnssec_validated": None,
        "registered_on": None,
        "updated_at": now,
    }
    db.execute(
        insert(BrandDomain)
        .values(brand_id=brand.id, created_at=now, **fresh)
        .on_conflict_do_update(index_elements=[BrandDomain.brand_id], set_=fresh)
    )
    db.commit()
    return get_mine(db, brand)


def get_mine(db: Session, brand: Brand) -> BrandDomain:
    """The brand's claim, or DomainClaimNotFound."""
    found = db.scalars(
        select(BrandDomain)
        .where(BrandDomain.brand_id == brand.id)
        .execution_options(populate_existing=True)
    ).first()
    if found is None:
        raise DomainClaimNotFound()
    return found


def withdraw(db: Session, brand: Brand) -> None:
    """Withdraw the claim: creators stop seeing the domain at once."""
    found = get_mine(db, brand)
    db.delete(found)
    db.commit()


def request_check(db: Session, brand: Brand, now: datetime) -> BrandDomain:
    """Ask for the record to be checked; the job does it within a minute.

    Raises DomainClaimNotFound, DomainClaimLapsed and DomainClaimExpired.
    Asking again before the check runs changes nothing.
    """
    found = db.scalars(
        select(BrandDomain).where(BrandDomain.brand_id == brand.id).with_for_update()
    ).first()
    if found is None:
        db.rollback()
        raise DomainClaimNotFound()
    if found.status == "lapsed":
        db.rollback()
        raise DomainClaimLapsed()
    if found.status == "pending" and now >= found.token_expires_at:
        db.rollback()
        raise DomainClaimExpired()
    if found.check_requested_at is None:
        found.check_requested_at = now
        found.updated_at = now
    db.commit()
    return found


def verified_for_brands(
    db: Session, brand_ids: Iterable[uuid.UUID]
) -> dict[uuid.UUID, BrandDomain]:
    """Each brand's verified domain, for any number of brands, in one query."""
    wanted = set(brand_ids)
    if not wanted:
        return {}
    rows = db.scalars(
        select(BrandDomain).where(
            BrandDomain.brand_id.in_(wanted), BrandDomain.status == "verified"
        )
    ).all()
    return {row.brand_id: row for row in rows}


# --- the checking job -------------------------------------------------------------------


@dataclass(frozen=True)
class DueCheck:
    """A claim taken for checking: what to look up, and which token to expect."""

    claim_id: uuid.UUID
    domain: str
    token: str
    needs_registration_date: bool


@dataclass(frozen=True)
class CheckRun:
    checked: int
    verified: int
    lapsed: int


def take_due(db: Session, now: datetime) -> list[DueCheck]:
    """Claims asked to be checked, and verified ones a day since their last check.

    Taken under SKIP LOCKED with a lease, so two runs never take the same
    claim. A pending claim whose token expired, or a lapsed one, has its
    request dropped instead: there is nothing a check could change.
    """
    rows = db.scalars(
        select(BrandDomain)
        .where(
            or_(
                BrandDomain.check_requested_at.is_not(None),
                and_(
                    BrandDomain.status == "verified",
                    BrandDomain.last_checked_at <= now - rules.RECHECK_AFTER,
                ),
            ),
            or_(
                BrandDomain.checking_since.is_(None),
                BrandDomain.checking_since < now - LEASE,
            ),
        )
        .order_by(
            BrandDomain.check_requested_at.asc().nulls_last(),
            BrandDomain.last_checked_at.asc(),
            BrandDomain.id,
        )
        .limit(BATCH_SIZE)
        .with_for_update(skip_locked=True)
    ).all()
    due: list[DueCheck] = []
    for row in rows:
        if row.status == "lapsed" or (
            row.status == "pending" and now >= row.token_expires_at
        ):
            row.check_requested_at = None
            row.updated_at = now
            continue
        row.checking_since = now
        due.append(
            DueCheck(
                claim_id=row.id,
                domain=row.domain,
                token=row.token,
                needs_registration_date=row.registered_on is None,
            )
        )
    db.commit()
    return due


def apply_check(
    db: Session,
    due: DueCheck,
    outcome: rules.CheckOutcome,
    registered_on: date | None,
    now: datetime,
) -> BrandDomain | None:
    """Record what a lookup found, if the claim still has the token looked up.

    Returns the claim, or None when it was withdrawn or claimed again while
    the lookup ran (its new token was not what was asked about).
    """
    row = _locked(db, due.claim_id)
    if row is None or row.token != due.token:
        db.rollback()
        return None
    result = outcome.result
    if (
        result == "found"
        and row.status == "pending"
        and _held_by_another(db, row.domain, row.brand_id)
    ):
        result = "taken"
    _record(row, result, outcome, registered_on, now)
    try:
        db.commit()
    except IntegrityError as error:
        # Another brand proved the same domain a moment ago.
        db.rollback()
        if UNIQUE_VERIFIED not in str(error):
            raise
        row = _locked(db, due.claim_id)
        if row is None or row.token != due.token:
            db.rollback()
            return None
        _record(row, "taken", outcome, registered_on, now)
        db.commit()
    return row


def run_checks(
    session_factory: Callable[[], AbstractContextManager[Session]],
    lookup: DomainLookup,
    now: datetime,
) -> CheckRun:
    """One run of the job: take, look up with no transaction open, apply."""
    with session_factory() as db:
        due = take_due(db, now)
    verified = lapsed = 0
    for check in due:
        outcome = rules.classify(lookup.txt(rules.record_name(check.domain)), check.token)
        registered_on = (
            lookup.registered_on(check.domain)
            if outcome.result == "found" and check.needs_registration_date
            else None
        )
        with session_factory() as db:
            before = db.get(BrandDomain, check.claim_id)
            was = before.status if before is not None else None
            row = apply_check(db, check, outcome, registered_on, now)
            if row is not None and row.status != was:
                verified += row.status == "verified"
                lapsed += row.status == "lapsed"
    logger.info(
        "brand_domain.checks checked=%d verified=%d lapsed=%d",
        len(due),
        verified,
        lapsed,
    )
    return CheckRun(checked=len(due), verified=verified, lapsed=lapsed)


def _locked(db: Session, claim_id: uuid.UUID) -> BrandDomain | None:
    return db.scalars(
        select(BrandDomain)
        .where(BrandDomain.id == claim_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).first()


def _record(
    row: BrandDomain,
    result: str,
    outcome: rules.CheckOutcome,
    registered_on: date | None,
    now: datetime,
) -> None:
    move = rules.after_check(row.status, row.consecutive_absent, result)
    row.status = move.status
    row.consecutive_absent = move.consecutive_absent
    if move.verified_now:
        row.verified_at = now
    if move.lapsed_now:
        row.lapsed_at = now
    if result == "found":
        row.dnssec_validated = outcome.dnssec_validated
    if registered_on is not None:
        row.registered_on = registered_on
    row.last_checked_at = now
    row.last_result = result
    row.check_requested_at = None
    row.checking_since = None
    row.updated_at = now


def _held_by_another(db: Session, domain: str, brand_id: uuid.UUID) -> bool:
    return (
        db.scalar(
            select(BrandDomain.id).where(
                BrandDomain.domain == domain,
                BrandDomain.status == "verified",
                BrandDomain.brand_id != brand_id,
            )
        )
        is not None
    )


# --- the brand's data export ----------------------------------------------------------

EXPORTED_TABLES = frozenset({"brand_domain"})
# Not the token: no field named for a token is ever released (app/core/
# export.py), and the brand reads its record from GET /brands/me/domain.
EXPORT_FIELDS = allow(
    "id",
    "domain",
    "status",
    "claimed_at",
    "last_checked_at",
    "last_result",
    "consecutive_absent",
    "verified_at",
    "lapsed_at",
    "registered_on",
    "dnssec_validated",
    "created_at",
    "updated_at",
)


def export_for_account(db: Session, account_id: uuid.UUID) -> list[ExportedSection]:
    """The brand's domain claim, if it has one."""
    rows = list(
        db.scalars(
            select(BrandDomain)
            .join(Brand, Brand.id == BrandDomain.brand_id)
            .where(Brand.account_id == account_id)
        ).all()
    )
    return [
        build_section(
            "website_domain",
            table="brand_domain",
            purpose=(
                "The website domain you claimed, the record we asked you to "
                "publish, and what each check found. Creators see the domain, "
                "since when it was verified and when it was registered."
            ),
            objects=rows,
            fields=EXPORT_FIELDS,
        )
    ]
