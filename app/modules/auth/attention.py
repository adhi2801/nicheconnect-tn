"""What about an account's own login is waiting on its owner (see app/core/attention.py)."""

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.attention import AttentionItem
from app.core.clock import india_date
from app.modules.auth.models.account_phone_change import AccountPhoneChange


def phone_change_for_account(
    db: Session, account_id: uuid.UUID, now: datetime
) -> list[AttentionItem]:
    """A new phone number still waiting its 72 hours (item 80, D-108).

    Due the day it takes over the login; gone once its wait is over, when it
    can no longer be cancelled, or once it is cancelled.
    """
    takes_effect_at = db.scalars(
        select(AccountPhoneChange.takes_effect_at).where(
            AccountPhoneChange.account_id == account_id,
            AccountPhoneChange.takes_effect_at > now,
        )
    ).first()
    if takes_effect_at is None:
        return []
    return [
        AttentionItem(
            kind="phone_change_pending",
            due_on=india_date(takes_effect_at),
            campaign_id=None,
            campaign_title=None,
        )
    ]
