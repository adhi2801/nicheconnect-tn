"""Where an account is logged in, and ending one session (item 81, D-114).

A session, to its owner, is one login: the family of refresh tokens that
login rotated through (D-008). Its id is the family's, which every access
token of it carries as `sid`. Only the family's latest row is live; its
creation is the last refresh, so "last active" is at most one access
token's 15 minutes behind the truth.

Ending one session lives in `me` (`me.session_service`), which spends the
code and tells the owner; the rules about which sessions are live, and
ending them, live here beside the other access checks.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import (
    ColumnElement,
    Select,
    Subquery,
    exists,
    func,
    literal,
    select,
    tuple_,
)
from sqlalchemy.orm import Session, aliased

from app.core.pagination import Slice, build_slice, decode_cursor
from app.modules.auth import service as login
from app.modules.auth.exceptions import SessionNotFound
from app.modules.auth.models.account import Account
from app.modules.auth.models.auth_session import AuthSession
from app.modules.auth.schemas import SignInMethod

# How long a new sign-in stays on its owner's attention list (D-114): long
# enough to be seen by someone who opens the app weekly.
RECENT_SIGN_IN = timedelta(days=7)


@dataclass(frozen=True)
class LiveSession:
    """One login still able to refresh, as its owner sees it."""

    id: uuid.UUID
    platform: str | None
    label: str | None
    signed_in_at: datetime
    last_active_at: datetime
    expires_at: datetime
    signed_in_with: SignInMethod


def _live(now: datetime) -> ColumnElement[bool]:
    """A family's latest row, still able to refresh: unused, not ended, not expired."""
    return (
        AuthSession.used_at.is_(None)
        & AuthSession.revoked_at.is_(None)
        & (AuthSession.expires_at > now)
    )


def account_for_token(
    db: Session, account_id: uuid.UUID, session_id: uuid.UUID | None
) -> tuple[Account | None, bool]:
    """The token's account, and whether its session is still live. One query.

    A session is ended when every row of its family is revoked, which is
    what every logout does (`service.end_sessions`). A token without a
    session id (signed before D-114) counts as live, as every token did
    before; it expires within 15 minutes of the release.
    """
    if session_id is None:
        return db.get(Account, account_id), True
    live = (
        exists()
        .where(
            AuthSession.family_id == session_id,
            AuthSession.account_id == Account.id,
            AuthSession.revoked_at.is_(None),
        )
        .label("live")
    )
    found = db.execute(select(Account, live).where(Account.id == account_id)).first()
    if found is None:
        return None, False
    return found[0], bool(found[1])


def _signed_in_with(row: AuthSession) -> SignInMethod:
    if row.second_factor_at is not None:
        return "two_factors"
    if row.passkey_at is not None:
        return "passkey"
    return "phone_code"


def _live_sessions(
    account_id: uuid.UUID, now: datetime
) -> tuple[Select[AuthSession, datetime], Subquery]:
    """The account's live rows, each with its sign-in time, newest sign-in first.

    The sign-in time is the family's first row (`service.logged_in_at`),
    read by a subquery on `ix_auth_session_family_id`, so the whole list is
    one statement whatever its length.
    """
    first = aliased(AuthSession)
    signed_in_at = (
        select(func.min(first.created_at))
        .where(first.family_id == AuthSession.family_id)
        .scalar_subquery()
        .label("signed_in_at")
    )
    live = (
        select(AuthSession, signed_in_at)
        .where(AuthSession.account_id == account_id, _live(now))
        .subquery()
    )
    row = aliased(AuthSession, live)
    statement = select(row, live.c.signed_in_at).order_by(
        live.c.signed_in_at.desc(), live.c.family_id.desc()
    )
    return statement, live


def _to_live(session: AuthSession, signed_in_at: datetime) -> LiveSession:
    return LiveSession(
        id=session.family_id,
        platform=session.client_platform,
        label=session.client_label,
        signed_in_at=signed_in_at,
        last_active_at=session.created_at,
        expires_at=session.expires_at,
        signed_in_with=_signed_in_with(session),
    )


def list_live(
    db: Session,
    account_id: uuid.UUID,
    now: datetime,
    *,
    limit: int,
    cursor: str | None = None,
) -> Slice[LiveSession]:
    """The account's live sessions, latest sign-in first, a keyset page. One query.

    Raises InvalidCursor for a cursor that was not ours.
    """
    statement, live = _live_sessions(account_id, now)
    if cursor is not None:
        after_at, after_id = decode_cursor(cursor)
        statement = statement.where(
            # Row values against literals, as `older_than_cursor` explains.
            tuple_(live.c.signed_in_at, live.c.family_id)
            < tuple_(literal(after_at), literal(after_id))
        )
    found = [
        _to_live(session, started)
        for session, started in db.execute(statement.limit(limit + 1)).all()
    ]
    return build_slice(found, limit, key=lambda item: (item.signed_in_at, item.id))


def recent_sign_ins(
    db: Session,
    account_id: uuid.UUID,
    now: datetime,
    *,
    excluding: uuid.UUID | None,
    limit: int,
) -> list[LiveSession]:
    """Live sessions signed in within `RECENT_SIGN_IN`, but not `excluding`. One query.

    For the attention list: a sign-in its owner did not make is the first
    sign of a SIM swap, and a list of sessions nobody opens tells nobody.
    """
    statement, live = _live_sessions(account_id, now)
    statement = statement.where(live.c.signed_in_at > now - RECENT_SIGN_IN)
    if excluding is not None:
        statement = statement.where(live.c.family_id != excluding)
    return [
        _to_live(session, started)
        for session, started in db.execute(statement.limit(limit)).all()
    ]


def ensure_live(
    db: Session, account_id: uuid.UUID, session_id: uuid.UUID, now: datetime
) -> AuthSession:
    """The session's live row; refused, as not found, if not this account's or not live.

    Another account's session reads exactly as one that never existed, so
    nobody learns another person's session ids (security.md section 2).
    """
    found = db.scalars(
        select(AuthSession)
        .where(
            AuthSession.account_id == account_id,
            AuthSession.family_id == session_id,
            _live(now),
        )
        .execution_options(populate_existing=True)
    ).first()
    if found is None:
        db.rollback()
        raise SessionNotFound()
    return found


def end_one(
    db: Session, account_id: uuid.UUID, session_id: uuid.UUID, now: datetime
) -> AuthSession:
    """End one of the account's live sessions, returning its last row. The caller commits.

    Locked first, as every way of ending a session is (`service.end_sessions`),
    so a refresh at the same moment cannot outlive it; then checked, under
    the lock, since another request may have ended it while this one waited.
    Raises SessionNotFound.
    """
    login.lock_sessions_of(db, account_id)
    found = ensure_live(db, account_id, session_id, now)
    login.end_sessions(db, account_id, now, family_id=session_id)
    return found
