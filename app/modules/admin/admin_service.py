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

from sqlalchemy import ColumnElement, func, literal, or_, select, tuple_
from sqlalchemy.orm import Session

from app.core.pagination import Slice, build_slice, decode_cursor, older_than_cursor
from app.modules.admin.exceptions import (
    AdminTargetNotAllowed,
    AlreadySuspended,
    NotSuspended,
    ReportAlreadyResolved,
    ReportNotFound,
)
from app.modules.admin.models.admin_action import AdminAction
from app.modules.admin.models.report import Report
from app.modules.auth import agent_tokens
from app.modules.auth import service as login
from app.modules.auth.exceptions import AdminNotFound
from app.modules.auth.models.account import Account
from app.modules.auth.models.brand import Brand
from app.modules.auth.models.creator import Creator
from app.modules.campaigns.models import Application, Campaign
from app.modules.deal_memo.models import DealMemo
from app.modules.notifications import service as notifications


def log_action(
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
        log_action(
            db, admin, "view_account", now, subject_account_id=account.id, note=reason
        )
    db.commit()
    return details


def account_detail(
    db: Session, admin: Account, account_id: uuid.UUID, *, reason: str, now: datetime
) -> AccountDetail:
    account = db.get(Account, account_id)
    if account is None:
        raise AdminNotFound("No such account.")
    detail = describe(db, account)
    log_action(db, admin, "view_account", now, subject_account_id=account.id, note=reason)
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
    """Stop the account at once, and end every session and assistant's token it has.

    Tokens are revoked, not only refused while suspended, so restoring an
    account taken over never brings the intruder's tokens back (D-138).
    """
    account = _target(db, admin, account_id)  # read with its row locked
    if account.suspended_at is not None:
        db.rollback()
        raise AlreadySuspended()
    account.suspended_at = now
    account.suspension_reason = reason
    login.end_sessions(db, account.id, now)
    agent_tokens.revoke_all(db, account.id, now)
    log_action(db, admin, "suspend", now, subject_account_id=account.id, note=note)
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
    log_action(db, admin, "restore", now, subject_account_id=account.id, note=note)
    db.commit()
    db.refresh(account)
    return account


# --- reports ------------------------------------------------------------------------------


def _after_cursor(cursor: str) -> ColumnElement[bool]:
    """Rows after `cursor` in nearest-deadline-first order: the queue's direction."""
    due_at, row_id = decode_cursor(cursor)
    return tuple_(Report.due_at, Report.id) > tuple_(literal(due_at), literal(row_id))


def list_reports(
    db: Session, *, status: str, limit: int, cursor: str | None
) -> Slice[Report]:
    """Nearest deadline first, so a 2-hour report filed now comes before a
    7-day one filed yesterday (item 51). Served by ix_report_status_due_at."""
    query = select(Report).where(Report.status == status)
    if cursor is not None:
        query = query.where(_after_cursor(cursor))
    rows = list(
        db.scalars(query.order_by(Report.due_at, Report.id).limit(limit + 1)).all()
    )
    return build_slice(rows, limit, key=lambda r: (r.due_at, r.id))


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
    log_action(db, admin, "resolve_report", now, report_id=report.id, note=note)
    # The reporter is told the outcome, in the same transaction (item 102).
    # Never the note, and never who handled it.
    notifications.record(
        db,
        account_id=report.reporter_account_id,
        notification_type="report_resolved",
        now=now,
        details={
            "report_id": str(report.id),
            "subject_kind": report.subject_kind,
            "outcome": outcome,
        },
    )
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
