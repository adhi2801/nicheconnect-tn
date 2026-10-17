"""What a waiting phone number change means for login (item 80, D-108).

The change itself is asked for, cancelled and made in `me.phone_change_service`,
which can tell the owner (notifications sit a layer above auth, D-099). Login
needs only to know that a number some account is waiting to move onto is
refused a new account, so the move cannot find it taken. A change touches
two numbers, so its work takes both per-phone locks (`service.lock_phones`).
"""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.auth.models.account_phone_change import AccountPhoneChange


def is_waiting_to_move(db: Session, phone: str) -> bool:
    """Whether some account is waiting to move onto `phone`."""
    return (
        db.scalars(
            select(AccountPhoneChange.id).where(AccountPhoneChange.new_phone == phone)
        ).first()
        is not None
    )


def is_due(change: AccountPhoneChange, now: datetime) -> bool:
    """Whether the change's 72 hours are over: from then it cannot be undone."""
    return now >= change.takes_effect_at
