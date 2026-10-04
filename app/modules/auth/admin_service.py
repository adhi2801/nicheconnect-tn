"""What an admin can do, each act written to the admin log (D-061).

Every look at an account's details, which include the phone number, is
logged as `view_account` in the same transaction that reads it, so there is
no path that shows a number without recording who looked and why. Admins
never see login codes, tokens, deal fees, dispute notes, or anything typed
into a deal.

An admin cannot suspend or restore another admin, or themself: that is a
founder's job, through scripts/make_admin.py.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import ColumnElement, func, literal, or_, select, tuple_, update
from sqlalchemy.orm import Session

from app.core.pagination import Slice, build_slice, decode_cursor, older_than_cursor
from app.modules.auth.exceptions import (
    AdminNotFound,
    AdminTargetNotAllowed,
    AlreadySuspended,
    NotSuspended,
    ReportAlreadyResolved,
    ReportNotFound,
)
from app.modules.auth.models.account import Account
from app.modules.auth.models.admin_action import AdminAction
from app.modules.auth.models.auth_session import AuthSession
from app.modules.auth.models.brand import Brand
from app.modules.auth.models.creator import Creator
from app.modules.auth.models.report import Report
from app.modules.campaigns.models import Application, Campaign
from app.modules.deal_memo.models import DealMemo


def _log(
    db: Session,
    admin: Account,
    action: str,
    now: datetime,
    *,
    subject_account_id: uuid.UUID | None = None,
    report_id: uuid.UUID | None = None,
    note: str | None = None,
) -> None:
    db.add(
        AdminAction(
            admin_account_id=admin.id,
            action=action,
            subject_account_id=subject_account_id,
            report_id=report_id,
            note=note,
            created_at=now,
        )
    )


# --- looking at accounts ---------------------------------------------------------------


@dataclass(frozen=True)
class AccountDetail:
    account: Account
    brand: Brand | None
    creator: Creator | None
    deals: int
    reports_about_open: int
    reports_about_total: int
    reports_made: int


def _subject_ids(
    brand: Brand | None, creator: Creator | None, db: Session
) -> list[uuid.UUID]:
    """Everything a report about this account could point at."""
    ids: list[uuid.UUID] = []
    if creator is not None:
        ids.append(creator.id)
    if brand is not None:
        ids.append(brand.id)
        ids += list(db.scalars(select(Campaign.id).where(Campaign.brand_id == brand.id)))
    return ids


def describe(db: Session, account: Account) -> AccountDetail:
    """The admin view of an account. Callers log the view; this does not."""
    brand = db.scalars(select(Brand).where(Brand.account_id == account.id)).first()
    creator = db.scalars(select(Creator).where(Creator.account_id == account.id)).first()

    deals_query = (
        select(func.count(DealMemo.id))
        .join(Application, Application.id == DealMemo.application_id)
        .join(Campaign, Campaign.id == Application.campaign_id)
    )
    if brand is not None:
        deals = db.scalar(deals_query.where(Campaign.brand_id == brand.id)) or 0
    elif creator is not None:
        deals = db.scalar(deals_query.where(Application.creator_id == creator.id)) or 0
    else:
        deals = 0

    subject_ids = _subject_ids(brand, creator, db)
    about_open = about_total = 0
    if subject_ids:
        about_total = (
            db.scalar(
                select(func.count(Report.id)).where(Report.subject_id.in_(subject_ids))
            )
            or 0
        )
        about_open = (
            db.scalar(
                select(func.count(Report.id)).where(
                    Report.subject_id.in_(subject_ids), Report.status == "open"
                )
            )
            or 0
        )
    made = (
        db.scalar(
            select(func.count(Report.id)).where(Report.reporter_account_id == account.id)
        )
        or 0
    )
    return AccountDetail(account, brand, creator, deals, about_open, about_total, made)


def find_accounts(
    db: Session,
    admin: Account,
    *,
    phone: str | None,
    handle: str | None,
    reason: str,
    now: datetime,
) -> list[AccountDetail]:
    """By phone, or by a creator's handle. Each account shown is logged."""
    query = select(Account)
    if phone is not None:
        query = query.where(Account.phone == phone)
    if handle is not None:
        query = query.join(Creator, Creator.account_id == Account.id).where(
            Creator.handle == handle.strip().lower().lstrip("@")
        )
    accounts = list(db.scalars(query.limit(5)).all())
    details = [describe(db, account) for account in accounts]
    for account in accounts:
        _log(db, admin, "view_account", now, subject_account_id=account.id, note=reason)
    db.commit()
    return details


def account_detail(
    db: Session, admin: Account, account_id: uuid.UUID, *, reason: str, now: datetime
) -> AccountDetail:
    account = db.get(Account, account_id)
    if account is None:
        raise AdminNotFound("No such account.")
    detail = describe(db, account)
    _log(db, admin, "view_account", now, subject_account_id=account.id, note=reason)
    db.commit()
    return detail


# --- suspending ---------------------------------------------------------------------------


def _target(db: Session, admin: Account, account_id: uuid.UUID) -> Account:
    account = db.get(Account, account_id, with_for_update=True)
    if account is None:
        db.rollback()
        raise AdminNotFound("No such account.")
    if account.role == "admin":
        db.rollback()
        raise AdminTargetNotAllowed()
    return account


def suspend(
    db: Session,
    admin: Account,
    account_id: uuid.UUID,
    *,
    reason: str,
    note: str,
    now: datetime,
) -> Account:
    """Stop the account at once, and end every session it has."""
    account = _target(db, admin, account_id)  # read with its row locked
    if account.suspended_at is not None:
        db.rollback()
        raise AlreadySuspended()
    account.suspended_at = now
    account.suspension_reason = reason
    db.execute(
        update(AuthSession)
        .where(AuthSession.account_id == account.id, AuthSession.revoked_at.is_(None))
        .values(revoked_at=now, updated_at=now)
    )
    _log(db, admin, "suspend", now, subject_account_id=account.id, note=note)
    db.commit()
    db.refresh(account)
    return account


def restore(
    db: Session, admin: Account, account_id: uuid.UUID, *, note: str, now: datetime
) -> Account:
    account = _target(db, admin, account_id)
    if account.suspended_at is None:
        db.rollback()
        raise NotSuspended()
    account.suspended_at = None
    account.suspension_reason = None
    _log(db, admin, "restore", now, subject_account_id=account.id, note=note)
    db.commit()
    db.refresh(account)
    return account


# --- reports ------------------------------------------------------------------------------


def _after_cursor(cursor: str) -> ColumnElement[bool]:
    """Rows after `cursor` in oldest-first order: the queue's direction."""
    created_at, row_id = decode_cursor(cursor)
    return tuple_(Report.created_at, Report.id) > tuple_(
        literal(created_at), literal(row_id)
    )


def list_reports(
    db: Session, *, status: str, limit: int, cursor: str | None
) -> Slice[Report]:
    """Oldest first, so the report waiting longest is handled first."""
    query = select(Report).where(Report.status == status)
    if cursor is not None:
        query = query.where(_after_cursor(cursor))
    rows = list(
        db.scalars(query.order_by(Report.created_at, Report.id).limit(limit + 1)).all()
    )
    return build_slice(rows, limit, key=lambda r: (r.created_at, r.id))


def resolve_report(
    db: Session,
    admin: Account,
    report_id: uuid.UUID,
    *,
    outcome: str,
    note: str,
    now: datetime,
) -> Report:
    report = db.get(Report, report_id, with_for_update=True)
    if report is None:
        db.rollback()
        raise ReportNotFound()
    if report.status != "open":
        db.rollback()
        raise ReportAlreadyResolved()
    report.status = outcome
    report.resolved_at = now
    report.resolution_note = note
    report.updated_at = now
    _log(db, admin, "resolve_report", now, report_id=report.id, note=note)
    db.commit()
    db.refresh(report)
    return report


# --- the log ------------------------------------------------------------------------------


def list_actions(
    db: Session,
    *,
    subject_account_id: uuid.UUID | None,
    limit: int,
    cursor: str | None,
) -> Slice[AdminAction]:
    """Newest first. Filter by subject to answer "who looked at this account?"."""
    query = select(AdminAction)
    if subject_account_id is not None:
        query = query.where(
            or_(
                AdminAction.subject_account_id == subject_account_id,
                AdminAction.admin_account_id == subject_account_id,
            )
        )
    if cursor is not None:
        query = query.where(
            older_than_cursor(AdminAction.created_at, AdminAction.id, cursor)
        )
    rows = list(
        db.scalars(
            query.order_by(AdminAction.created_at.desc(), AdminAction.id.desc()).limit(
                limit + 1
            )
        ).all()
    )
    return build_slice(rows, limit, key=lambda a: (a.created_at, a.id))
