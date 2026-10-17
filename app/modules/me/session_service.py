"""Logging out of every device, after a second check (item 82, D-107).

Here rather than in `auth` because the owner is told, and notifications sit
a layer above auth (D-099).

Why it needs a code (ASVS 5.0 7.5.2): someone holding a stolen session
could otherwise log the owner out of every device and keep the account to
themselves. With the code, the owner, who has the phone, can still throw
them out, and they cannot throw out the owner. Someone who has taken over
the number can do both, so the owner is told in the app either way.
"""

from datetime import datetime

from sqlalchemy.orm import Session

from app.modules.auth import service as login
from app.modules.auth import step_up_service as step_ups
from app.modules.auth.models.account import Account
from app.modules.notifications import service as notifications


def log_out_everywhere(
    db: Session, account: Account, step_up_code: str | None, now: datetime
) -> int:
    """End every session of the account and stop its push. Commits.

    Returns how many sessions were still active. Raises what
    step_up_service.consume raises.
    """
    step_ups.consume(db, account, "log_out_everywhere", "", step_up_code, now)
    ended = login.logout_all_sessions(db, account.id, now)
    notifications.record(
        db,
        account_id=account.id,
        notification_type="logged_out_everywhere",
        now=now,
        details={"sessions_ended": ended},
    )
    db.commit()
    return ended
