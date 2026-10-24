"""Where you are logged in: listing sessions, ending one, ending all (items 81, 82).

Here rather than in `auth` because the owner is told, and notifications sit
a layer above auth (D-099). Which sessions are live, and ending them, are
`auth.sessions`' rules.

Why ending another session needs a code (ASVS 5.0 7.5.2): someone holding a
stolen session could otherwise log the owner out and keep the account to
themselves. With the code, the owner, who has the phone, can still throw
them out, and they cannot throw out the owner. Someone who has taken over
the number can do both, so the owner is told in the app either way. Ending
your own session needs none: it is logging out, and a thief who does it
only throws out themselves.
"""

import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from app.core.pagination import Slice
from app.modules.auth import service as login
from app.modules.auth import sessions
from app.modules.auth import step_up_service as step_ups
from app.modules.auth.models.account import Account
from app.modules.auth.sessions import LiveSession
from app.modules.notifications import service as notifications


def list_mine(
    db: Session, account: Account, now: datetime, *, limit: int, cursor: str | None
) -> Slice[LiveSession]:
    """The account's live sessions, latest sign-in first. Raises InvalidCursor."""
    return sessions.list_live(db, account.id, now, limit=limit, cursor=cursor)


def end_one(
    db: Session,
    account: Account,
    session_id: uuid.UUID,
    current_session_id: uuid.UUID | None,
    step_up_code: str | None,
    now: datetime,
) -> None:
    """End one live session of the account. Commits.

    This device's own session ends with no code, as a logout. Any other
    needs a code for exactly that session (`end_session`, item 82), and the
    owner is told, by a notification nobody can mute. Raises
    SessionNotFound (not theirs, or not live: the code is not spent) and
    what step_up_service.consume raises.
    """
    if session_id == current_session_id:
        sessions.end_one(db, account.id, session_id, now)
        db.commit()
        return
    # Not found before a code is asked for, so a stranger's guess at an id is
    # answered as any other route answers it (security.md section 2).
    sessions.ensure_live(db, account.id, session_id, now)
    step_ups.consume(db, account, "end_session", str(session_id), step_up_code, now)
    ended = sessions.end_one(db, account.id, session_id, now)
    notifications.record(
        db,
        account_id=account.id,
        notification_type="session_ended",
        now=now,
        details={
            "session_id": str(session_id),
            "device_platform": ended.client_platform,
            "device_label": ended.client_label,
        },
    )
    db.commit()


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


def acknowledge(
    db: Session,
    account: Account,
    session_id: uuid.UUID,
    current_session_id: uuid.UUID | None,
    now: datetime,
) -> None:
    """Say a sign-in was yours, from a session that signed in before it (D-120). Commits.

    Raises SessionNotFound and AcknowledgeNotAllowed.
    """
    sessions.acknowledge(db, account.id, session_id, current_session_id, now)
    db.commit()
