"""Admins withholding one item, and lifting it, each act in the admin log (item 52, D-104).

On a court order or government notice (rule 3(1)(d), 3 hours), or on a report
the IT Rules make us act on (item 51's clocks), an admin withholds exactly
one creator profile, brand or campaign. Everyone else stops seeing it at once
(safety/takedowns.py); its owner keeps the account, sees the item, and is
told, in the same transaction, so nothing is ever withheld silently.

**What makes it trustworthy:**

- `withheld_at` is the server's clock, never typed, so "were we within 3
  hours?" has an answer nobody can adjust; `received_at` is read from the
  order and must be a real moment in the last 30 days;
- the item's visible text is copied into the takedown as it stood
  (`preserved`), which the IT Rules ask us to keep (rule 3(1)(g)); an edit
  afterwards cannot destroy it;
- one active takedown per item, held by the database, so two admins acting
  on the same order at once make one takedown, and the other gets 409;
- every withhold and lift is in the sealed admin log with the admin's note.

Whether a report-based takedown resolves its report is the admin's separate
decision (POST /admin/reports/{id}/resolve): withholding while looking into
it is not a finding.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.export import to_json_value
from app.core.pagination import Slice, build_slice, older_than_cursor
from app.modules.admin import takedown_clocks
from app.modules.admin.admin_service import log_action
from app.modules.admin.exceptions import (
    AlreadyWithheld,
    OrderTimeNotPossible,
    ReportNamesAnotherItem,
    ReportNotFound,
    TakedownAlreadyLifted,
    TakedownNotFound,
    TakedownSubjectNotFound,
)
from app.modules.admin.models.report import Report
from app.modules.auth.models.account import Account
from app.modules.auth.models.brand import Brand
from app.modules.auth.models.creator import Creator
from app.modules.campaigns.models import Campaign
from app.modules.notifications import service as notifications
from app.modules.profiles.models import CreatorChannel, CreatorPackage
from app.modules.safety.takedown_models import Takedown

# A brand's open campaigns kept by id and title in its preserved copy. Their
# own text is not: an order against a brand is about the brand, and each
# campaign can be withheld, and preserved, on its own.
PRESERVED_CAMPAIGNS = 50


@dataclass(frozen=True)
class Order:
    """What the admin read from the order. None for a report-based takedown."""

    basis: str  # court_order or government_notice
    issued_by: str
    order_reference: str
    legal_provision: str | None
    reference_sealed: bool
    received_at: datetime


# --- what is withheld --------------------------------------------------------------------


def _campaign_text(campaign: Campaign) -> dict[str, Any]:
    return {
        "title": campaign.title,
        "description": campaign.description,
        "deliverables": campaign.deliverables,
        "campaign_type": campaign.campaign_type,
        "cities": campaign.cities,
        "niches": campaign.niches,
        "status": campaign.status,
    }


def _creator_text(db: Session, creator: Creator) -> dict[str, Any]:
    """What the Passport and the media kit show: the profile, links, packages."""
    channels = db.scalars(
        select(CreatorChannel)
        .where(CreatorChannel.creator_id == creator.id)
        .order_by(CreatorChannel.platform)
    ).all()
    packages = db.scalars(
        select(CreatorPackage)
        .where(CreatorPackage.creator_id == creator.id)
        .order_by(CreatorPackage.position, CreatorPackage.id)
    ).all()
    return {
        "display_name": creator.display_name,
        "handle": creator.handle,
        "city": creator.city,
        "niches": creator.niches,
        "languages": creator.languages,
        "bio": creator.bio,
        "channels": [
            {"platform": c.platform, "profile_url": c.profile_url} for c in channels
        ],
        "packages": [{"title": p.title, "description": p.description} for p in packages],
    }


def _brand_text(db: Session, brand: Brand) -> dict[str, Any]:
    """The name creators see, and which open campaigns it reached.

    Never the brand's email: it is contact detail, not something shown.
    """
    campaigns = db.execute(
        select(Campaign.id, Campaign.title)
        .where(Campaign.brand_id == brand.id, Campaign.status == "open")
        .order_by(Campaign.created_at.desc(), Campaign.id.desc())
        .limit(PRESERVED_CAMPAIGNS + 1)
    ).all()
    return {
        "name": brand.name,
        "open_campaigns": [
            {"id": str(row.id), "title": row.title}
            for row in campaigns[:PRESERVED_CAMPAIGNS]
        ],
        "more_open_campaigns": len(campaigns) > PRESERVED_CAMPAIGNS,
    }


def _subject(
    db: Session, subject_kind: str, subject_id: uuid.UUID
) -> tuple[uuid.UUID, dict[str, Any]]:
    """The owner's account and the item's visible text, as it stands now.

    Raises TakedownSubjectNotFound.
    """
    if subject_kind == "campaign":
        row = db.execute(
            select(Campaign, Brand.account_id)
            .join(Brand, Brand.id == Campaign.brand_id)
            .where(Campaign.id == subject_id)
        ).first()
        if row is not None:
            return row[1], _campaign_text(row[0])
    elif subject_kind == "creator":
        creator = db.get(Creator, subject_id)
        if creator is not None:
            return creator.account_id, _creator_text(db, creator)
    else:
        brand = db.get(Brand, subject_id)
        if brand is not None:
            return brand.account_id, _brand_text(db, brand)
    raise TakedownSubjectNotFound()


# --- placing and lifting -----------------------------------------------------------------


def _clock(
    db: Session,
    *,
    order: Order | None,
    report_id: uuid.UUID | None,
    subject_kind: str,
    subject_id: uuid.UUID,
    now: datetime,
) -> tuple[datetime, datetime]:
    """When it reached us and when it is due. Raises the 404 and 422s."""
    report = None
    if report_id is not None:
        report = db.get(Report, report_id)
        if report is None:
            raise ReportNotFound()
        if (report.subject_kind, report.subject_id) != (subject_kind, subject_id):
            raise ReportNamesAnotherItem()
    if order is None:
        # A report-based takedown: the report's own clock (item 51). The
        # schema makes report_id required here.
        if report is None:
            raise ReportNotFound()
        return report.created_at, report.due_at
    received = order.received_at
    if received > now or received < now - takedown_clocks.OLDEST_ORDER:
        raise OrderTimeNotPossible()
    return received, takedown_clocks.order_due_at(received)


def withhold(
    db: Session,
    admin: Account,
    *,
    subject_kind: str,
    subject_id: uuid.UUID,
    order: Order | None,
    report_id: uuid.UUID | None,
    note: str,
    now: datetime,
) -> Takedown:
    """Withhold one item from everyone but its owner, and tell the owner.

    Raises TakedownSubjectNotFound, ReportNotFound, ReportNamesAnotherItem,
    OrderTimeNotPossible and AlreadyWithheld.
    """
    # Reads only, with nothing locked, so a refusal here needs no rollback.
    owner_account_id, preserved = _subject(db, subject_kind, subject_id)
    received_at, due_at = _clock(
        db,
        order=order,
        report_id=report_id,
        subject_kind=subject_kind,
        subject_id=subject_id,
        now=now,
    )
    takedown = Takedown(
        subject_kind=subject_kind,
        subject_id=subject_id,
        owner_account_id=owner_account_id,
        basis="report" if order is None else order.basis,
        issued_by=None if order is None else order.issued_by,
        order_reference=None if order is None else order.order_reference,
        legal_provision=None if order is None else order.legal_provision,
        reference_sealed=False if order is None else order.reference_sealed,
        report_id=report_id,
        received_at=received_at,
        due_at=due_at,
        withheld_at=now,
        withheld_by_account_id=admin.id,
        preserved=to_json_value(preserved),
        created_at=now,
        updated_at=now,
    )
    db.add(takedown)
    try:
        # One active takedown per item: a second, at once or later, is
        # refused here by uq_takedown_active_subject.
        db.flush()
    except IntegrityError as error:
        db.rollback()
        if "uq_takedown_active_subject" not in str(error):
            raise
        raise AlreadyWithheld() from error
    log_action(
        db,
        admin,
        "withhold",
        now,
        subject_account_id=owner_account_id,
        report_id=report_id,
        note=note,
    )
    # The owner is told in the same transaction: nothing is withheld silently.
    notifications.record(
        db,
        account_id=owner_account_id,
        notification_type="content_withheld",
        now=now,
        details={
            "takedown_id": str(takedown.id),
            "subject_kind": subject_kind,
            "subject_id": str(subject_id),
            "basis": takedown.basis,
        },
    )
    db.commit()
    db.refresh(takedown)
    return takedown


def lift(
    db: Session, admin: Account, takedown_id: uuid.UUID, *, note: str, now: datetime
) -> Takedown:
    """Make the item visible again, and tell the owner.

    Raises TakedownNotFound and TakedownAlreadyLifted. Read under its row's
    lock, so two lifts at once make one.
    """
    takedown = db.get(Takedown, takedown_id, with_for_update=True)
    if takedown is None:
        db.rollback()
        raise TakedownNotFound()
    if takedown.lifted_at is not None:
        db.rollback()
        raise TakedownAlreadyLifted()
    takedown.lifted_at = now
    takedown.lifted_by_account_id = admin.id
    takedown.updated_at = now
    log_action(
        db,
        admin,
        "lift_withhold",
        now,
        subject_account_id=takedown.owner_account_id,
        report_id=takedown.report_id,
        note=note,
    )
    notifications.record(
        db,
        account_id=takedown.owner_account_id,
        notification_type="content_restored",
        now=now,
        details={
            "takedown_id": str(takedown.id),
            "subject_kind": takedown.subject_kind,
            "subject_id": str(takedown.subject_id),
        },
    )
    db.commit()
    db.refresh(takedown)
    return takedown


def list_takedowns(
    db: Session, *, active: bool | None, limit: int, cursor: str | None
) -> Slice[Takedown]:
    """Newest first; `active` keeps only those still withheld, or only lifted."""
    query = select(Takedown)
    if active is True:
        query = query.where(Takedown.lifted_at.is_(None))
    elif active is False:
        query = query.where(Takedown.lifted_at.is_not(None))
    if cursor is not None:
        query = query.where(older_than_cursor(Takedown.created_at, Takedown.id, cursor))
    rows = list(
        db.scalars(
            query.order_by(Takedown.created_at.desc(), Takedown.id.desc()).limit(
                limit + 1
            )
        ).all()
    )
    return build_slice(rows, limit, key=lambda t: (t.created_at, t.id))
