"""What about an account's own login is waiting on its owner (see app/core/attention.py)."""

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.attention import MAX_ITEMS, NEW_SIGN_IN, AttentionItem
from app.core.clock import india_date
from app.modules.auth import phone_changes, sessions
from app.modules.auth.models.account_phone_change import AccountPhoneChange


def phone_change_for_account(
    db: Session, account_id: uuid.UUID, now: datetime
) -> list[AttentionItem]:
    """A new phone number still waiting its 72 hours (item 80, D-108).

    Due the day it takes over the login; gone once its wait is over, when it
    can no longer be cancelled, once it is cancelled, or, for one made
    without the current number, once that number has logged in (D-110).
    """
    change = db.scalars(
        select(AccountPhoneChange).where(
            AccountPhoneChange.account_id == account_id,
            AccountPhoneChange.takes_effect_at > now,
        )
    ).first()
    if change is None or phone_changes.is_void(db, change):
        return []
    takes_effect_at = change.takes_effect_at
    return [
        AttentionItem(
            kind="phone_change_pending",
            due_on=india_date(takes_effect_at),
            campaign_id=None,
            campaign_title=None,
        )
    ]


def new_sign_ins_for_account(
    db: Session,
    account_id: uuid.UUID,
    current_session_id: uuid.UUID | None,
    now: datetime,
) -> list[AttentionItem]:
    """Sign-ins in the last 7 days, other than the one asking (item 81, D-114).

    Each still live; gone once it is ended, or 7 days after it signed in.
    At most MAX_ITEMS, all the list can show, so beyond that many sign-ins
    in a week `counts` stops at 50; one query.
    """
    return [
        AttentionItem(
            kind=NEW_SIGN_IN,
            due_on=None,
            campaign_id=None,
            campaign_title=None,
            session_id=found.id,
            signed_in_at=found.signed_in_at,
            device_platform=found.platform,
            device_label=found.label,
            signed_in_with=found.signed_in_with,
        )
        for found in sessions.recent_sign_ins(
            db, account_id, now, excluding=current_session_id, limit=MAX_ITEMS
        )
    ]
