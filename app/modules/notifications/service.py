"""Notification rules: record what happened, for one account (D-023).

Creating a notification never sends anything by itself. Delivery (WhatsApp
alerts, D-022) is a separate step that reads these rows, so a failure to
deliver can never lose the record or break the action that caused it.
"""

import uuid
from datetime import datetime
from typing import Any, cast

from sqlalchemy import CursorResult, func, select, update
from sqlalchemy.orm import Session

from app.core.export import (
    MAX_ROWS_PER_SECTION,
    ExportedSection,
    allow,
    build_section,
)
from app.core.pagination import Slice, build_slice, older_than_cursor
from app.modules.notifications.models import Notification

# Tables this module answers for in a data export. The completeness test in
# tests/modules/auth/test_export_api.py reads this, so a new table here
# cannot be left out of an export by accident.
EXPORTED_TABLES = frozenset({"notification"})

EXPORT_FIELDS = allow(
    "id",
    "notification_type",
    "campaign_id",
    "application_id",
    "details",
    "read_at",
    "created_at",
    "updated_at",
)


def record(
    db: Session,
    *,
    account_id: uuid.UUID,
    notification_type: str,
    now: datetime,
    campaign_id: uuid.UUID | None = None,
    application_id: uuid.UUID | None = None,
    details: dict[str, Any] | None = None,
) -> Notification:
    """Add a notification. The caller commits, as part of its own work."""
    notification = Notification(
        account_id=account_id,
        notification_type=notification_type,
        campaign_id=campaign_id,
        application_id=application_id,
        details=details or {},
        created_at=now,
        updated_at=now,
    )
    db.add(notification)
    return notification


def list_for_account(
    db: Session,
    account_id: uuid.UUID,
    *,
    limit: int,
    cursor: str | None = None,
    unread_only: bool = False,
) -> Slice[Notification]:
    """One account's notifications, newest first."""
    query = select(Notification).where(Notification.account_id == account_id)
    if unread_only:
        query = query.where(Notification.read_at.is_(None))
    if cursor is not None:
        query = query.where(
            older_than_cursor(Notification.created_at, Notification.id, cursor)
        )
    rows = list(
        db.scalars(
            query.order_by(Notification.created_at.desc(), Notification.id.desc()).limit(
                limit + 1
            )
        ).all()
    )
    return build_slice(rows, limit, key=lambda row: (row.created_at, row.id))


def unread_count(db: Session, account_id: uuid.UUID) -> int:
    # COUNT always returns a row; `or 0` only settles the Optional type.
    count = db.scalar(
        select(func.count())
        .select_from(Notification)
        .where(Notification.account_id == account_id, Notification.read_at.is_(None))
    )
    return count or 0


def mark_read(db: Session, notification: Notification, now: datetime) -> Notification:
    """Mark one as read. Reading it again keeps the first time."""
    if notification.read_at is None:
        notification.read_at = now
        notification.updated_at = now
        db.commit()
        db.refresh(notification)
    else:
        db.rollback()
    return notification


def mark_all_read(db: Session, account_id: uuid.UUID, now: datetime) -> int:
    """Mark every unread notification read. Returns how many changed."""
    # SQLAlchemy types Session.execute() as Result[Any], which has no rowcount.
    # An UPDATE returns a CursorResult at runtime, and that is where rowcount
    # lives; the cast is type-checker-only and emits no runtime code.
    result = cast(
        "CursorResult[Any]",
        db.execute(
            update(Notification)
            .where(Notification.account_id == account_id, Notification.read_at.is_(None))
            .values(read_at=now, updated_at=now)
        ),
    )
    db.commit()
    return result.rowcount


def export_for_account(db: Session, account_id: uuid.UUID) -> list[ExportedSection]:
    """This account's notifications, for a data export.

    `details` holds only the campaign title and the other side's public
    handle, so nothing private about anyone else travels with it.
    """
    rows = list(
        db.scalars(
            select(Notification)
            .where(Notification.account_id == account_id)
            .order_by(Notification.created_at, Notification.id)
            .limit(MAX_ROWS_PER_SECTION + 1)
        ).all()
    )
    return [
        build_section(
            "notifications",
            table="notification",
            purpose=(
                "Alerts we raised for you about campaigns, applications, deal "
                "memos and proof of work, so you can see what happened and when."
            ),
            objects=rows,
            fields=EXPORT_FIELDS,
        )
    ]
