"""Notification rules: record what happened, for one account (D-023).

Creating a notification never sends anything by itself. Delivery (WhatsApp
alerts, D-022) is a separate step that reads these rows, so a failure to
deliver can never lose the record or break the action that caused it.

A brand is a team (D-148 piece 2): a notice to a brand's owner about the
work is copied to each live member whose role holds that work's act
(`auth.brand_acts.NOTICE_ACTS`), never to whoever on the team did it; and a
creator told of a member's act is shown that member's first name. The
notice keeps the membership's id, never the name: the name is read when the
notice is (`readable_details`), so erasing a member erases it everywhere.
"""

import uuid
from datetime import datetime
from typing import Any, cast

from sqlalchemy import CursorResult, func, select, update
from sqlalchemy import delete as sa_delete
from sqlalchemy.orm import Session

from app.core.export import (
    MAX_ROWS_PER_SECTION,
    ExportedSection,
    allow,
    build_section,
)
from app.core.pagination import Slice, build_slice, older_than_cursor
from app.modules.auth import brand_access, brand_acts
from app.modules.auth.models.account import Account
from app.modules.auth.models.brand import Brand
from app.modules.auth.models.brand_team import BrandMember
from app.modules.notifications.exceptions import NotificationNotFound
from app.modules.notifications.models import Notification
from app.modules.notifications.preference_models import NotificationPreference

# Tables this module answers for in a data export. The completeness test in
# tests/modules/me/test_export_api.py reads this, so a new table here
# cannot be left out of an export by accident.
EXPORTED_TABLES = frozenset({"notification"})

# Where a notice keeps the team member who acted (D-148): their membership.
ACTING_MEMBER = "acting_member_id"

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
    """Add a notification, and its copies to the brand's team. The caller
    commits, as part of its own work.

    At most two queries more, and only when a member acts or the notice is
    one a team hears: who the recipient is, and the team.
    """
    shown = dict(details or {})
    acting = brand_access.acting(db)
    if (
        acting is not None
        and acting.member_id is not None
        and notification_type in brand_acts.NAMED_TO_CREATORS
        and account_id != acting.account_id
    ):
        recipient = db.get(Account, account_id)
        if recipient is not None and recipient.role == "creator":
            shown[ACTING_MEMBER] = str(acting.member_id)
    notification = _add(
        db, account_id, notification_type, now, campaign_id, application_id, shown
    )
    roles = brand_acts.roles_hearing(notification_type)
    if roles:
        team = db.execute(
            select(BrandMember.account_id, Brand.id, Brand.name)
            .join(Brand, Brand.id == BrandMember.brand_id)
            .join(Account, Account.id == BrandMember.account_id)
            .where(
                Brand.account_id == account_id,
                BrandMember.removed_at.is_(None),
                BrandMember.role.in_(roles),
                # A suspended or departed member acts for nobody, so hears nothing.
                Account.suspended_at.is_(None),
                Account.deleted_at.is_(None),
            )
            .order_by(BrandMember.created_at, BrandMember.id)
        ).all()
        for member_account, brand_id, brand_name in team:
            if acting is not None and member_account == acting.account_id:
                continue
            _add(
                db,
                member_account,
                notification_type,
                now,
                campaign_id,
                application_id,
                # Someone in several brands needs to know which one it is for.
                {**shown, "for_brand_id": str(brand_id), "for_brand_name": brand_name},
            )
    return notification


def readable_details(db: Session, rows: list[Notification]) -> list[dict[str, Any]]:
    """Each notification's details as its reader sees them, in one query at most.

    A member's act names them by their first name, read now from their
    membership, whether or not they are still on the team; a membership
    erased with its account names nobody.
    """
    members = {row.details[ACTING_MEMBER] for row in rows if ACTING_MEMBER in row.details}
    names: dict[str, str] = {}
    if members:
        names = {
            str(member_id): first_name
            for member_id, first_name in db.execute(
                select(BrandMember.id, BrandMember.first_name).where(
                    BrandMember.id.in_([uuid.UUID(m) for m in members])
                )
            ).all()
        }
    shown = []
    for row in rows:
        details = {k: v for k, v in row.details.items() if k != ACTING_MEMBER}
        name = names.get(row.details.get(ACTING_MEMBER, ""))
        if name is not None:
            details["acting_first_name"] = name
        shown.append(details)
    return shown


def _add(
    db: Session,
    account_id: uuid.UUID,
    notification_type: str,
    now: datetime,
    campaign_id: uuid.UUID | None,
    application_id: uuid.UUID | None,
    details: dict[str, Any],
) -> Notification:
    notification = Notification(
        account_id=account_id,
        notification_type=notification_type,
        campaign_id=campaign_id,
        application_id=application_id,
        details=details,
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


def get_own(
    db: Session, notification_id: uuid.UUID, account_id: uuid.UUID
) -> Notification:
    """A notification belonging to this account.

    Raises NotificationNotFound for an unknown id or someone else's, never
    403, so its existence is not confirmed.
    """
    notification = db.scalars(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.account_id == account_id,
        )
    ).first()
    if notification is None:
        raise NotificationNotFound()
    return notification


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

    `details` holds rendering values: a campaign title, the other side's
    public handle, a brand's name, and, for a team member's act, their
    membership's id, never their name or number, so nothing private about
    anyone else travels with it.
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


def erase_for_account(db: Session, account_id: uuid.UUID) -> None:
    """On deleting the account (D-122): every notification and its preferences. Never commits."""
    db.execute(sa_delete(Notification).where(Notification.account_id == account_id))
    db.execute(
        sa_delete(NotificationPreference).where(
            NotificationPreference.account_id == account_id
        )
    )
