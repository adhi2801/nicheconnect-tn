"""What a waiting phone number change means for login (item 80, D-108).

The change itself is asked for, cancelled and made in `me.phone_change_service`,
which can tell the owner (notifications sit a layer above auth, D-099). Login
needs only to know that a number some account is waiting to move onto is
refused a new account, so the move cannot find it taken; and a change made
without a code from the current number is off once that number logs in
(`is_void`). A change touches two numbers, so its work takes both per-phone
locks (`service.lock_phones`).
"""

import uuid
from collections.abc import Iterable
from datetime import datetime

from sqlalchemy import exists, func, select
from sqlalchemy.orm import Session

from app.modules.auth.models.account import Account
from app.modules.auth.models.account_phone_change import AccountPhoneChange
from app.modules.auth.models.auth_session import AuthSession


def is_waiting_to_move(db: Session, phone: str) -> bool:
    """Whether some account is waiting to move onto `phone`."""
    return (
        db.scalars(
            select(AccountPhoneChange.id).where(AccountPhoneChange.new_phone == phone)
        ).first()
        is not None
    )


def any_waiting(db: Session, account_ids: Iterable[uuid.UUID]) -> bool:
    """Whether any of these accounts is waiting to move to a new number."""
    ids = list(account_ids)
    return bool(ids) and bool(
        db.scalar(select(exists().where(AccountPhoneChange.account_id.in_(ids))))
    )


def is_void(db: Session, change: AccountPhoneChange) -> bool:
    """Whether the current number has logged in since a change made without it.

    Only for a change asked for without a code from the current number
    (D-110): if anyone could log in with that number afterwards, it was not
    lost, so the change is off. A login starts a new session family, and
    nothing else does (a refresh adds to its own), so a family whose first
    row is no older than the request is such a login. A login to the other
    side of the same number counts as well (D-126): it proves the number too.
    """
    if not change.without_current_number:
        return False
    number = (
        select(Account.phone).where(Account.id == change.account_id).scalar_subquery()
    )
    on_number = select(Account.id).where(Account.phone == number)
    return (
        db.scalars(
            select(AuthSession.family_id)
            .where(AuthSession.account_id.in_(on_number))
            .group_by(AuthSession.family_id)
            .having(func.min(AuthSession.created_at) >= change.requested_at)
            .limit(1)
        ).first()
        is not None
    )


def is_due(change: AccountPhoneChange, now: datetime) -> bool:
    """Whether the change's 72 hours are over: from then it cannot be undone."""
    return now >= change.takes_effect_at
