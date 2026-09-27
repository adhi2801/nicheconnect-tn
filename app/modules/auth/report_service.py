"""Users reporting a creator, a brand or a campaign (D-061).

A report must point at something that exists; nobody may report
themselves; and a second report of the same thing while the first is open
changes nothing and says so, rather than filling the queue with duplicates.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.auth.exceptions import CannotReportYourself, ReportSubjectNotFound
from app.modules.auth.models.account import Account
from app.modules.auth.models.brand import Brand
from app.modules.auth.models.creator import Creator
from app.modules.auth.models.report import Report
from app.modules.campaigns.models import Campaign


@dataclass(frozen=True)
class Filed:
    report: Report
    already_open: bool


def _owner_account_id(db: Session, subject_kind: str, subject_id: uuid.UUID) -> uuid.UUID:
    """The account behind the subject. Raises ReportSubjectNotFound."""
    if subject_kind == "creator":
        owner = db.scalar(select(Creator.account_id).where(Creator.id == subject_id))
    elif subject_kind == "brand":
        owner = db.scalar(select(Brand.account_id).where(Brand.id == subject_id))
    else:
        owner = db.scalar(
            select(Brand.account_id)
            .join(Campaign, Campaign.brand_id == Brand.id)
            .where(Campaign.id == subject_id)
        )
    if owner is None:
        raise ReportSubjectNotFound()
    return owner


def _open_report(
    db: Session, reporter: Account, subject_kind: str, subject_id: uuid.UUID
) -> Report | None:
    return db.scalars(
        select(Report).where(
            Report.reporter_account_id == reporter.id,
            Report.subject_kind == subject_kind,
            Report.subject_id == subject_id,
            Report.status == "open",
        )
    ).first()


def file_report(
    db: Session,
    reporter: Account,
    *,
    subject_kind: str,
    subject_id: uuid.UUID,
    category: str,
    note: str | None,
    now: datetime,
) -> Filed:
    if _owner_account_id(db, subject_kind, subject_id) == reporter.id:
        raise CannotReportYourself()

    existing = _open_report(db, reporter, subject_kind, subject_id)
    if existing is not None:
        return Filed(existing, already_open=True)

    report = Report(
        reporter_account_id=reporter.id,
        subject_kind=subject_kind,
        subject_id=subject_id,
        category=category,
        note=note,
        status="open",
        created_at=now,
        updated_at=now,
    )
    db.add(report)
    try:
        db.commit()
    except IntegrityError:
        # Two taps at once: the partial unique index let only one through.
        db.rollback()
        found = _open_report(db, reporter, subject_kind, subject_id)
        if found is None:
            raise
        return Filed(found, already_open=True)
    db.refresh(report)
    return Filed(report, already_open=False)
