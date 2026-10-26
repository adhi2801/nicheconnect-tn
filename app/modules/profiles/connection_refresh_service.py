"""Keeping connected accounts current (item 29 piece 2, D-134): the rules.

Once a day (`me.connection_jobs`), each active connection is read again:

- **Instagram** gives a 60-day token, renewed only once it is at least a day
  old and before it lapses (a lapsed one cannot be renewed). Ours is renewed
  once 30 days or fewer remain, so a missed day or two never loses it.
- **Google** gives an hour-long access token and a refresh token; a fresh
  access token is fetched from it each run.
- Then the count is read again, and stored with its time.

A platform that refuses (the creator removed our app, changed their
password, or a token lapsed) marks the connection `expired`, and the caller
is told in the same transaction (`on_expired`), so the creator hears exactly
once. A platform that does not answer is left alone and tried the next day.
No platform is asked inside a transaction; the connection is re-read under
its lock before writing, and one reconnected or removed meanwhile is left
as it now is.
"""

import logging
import uuid
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.modules.profiles import connection_secrets as vault
from app.modules.profiles import platform_clients
from app.modules.profiles.connection_models import ConnectedAccount
from app.modules.profiles.connection_service import token_context, tokens_of
from app.modules.profiles.platform_clients import (
    PlatformRefused,
    PlatformUnavailable,
)

logger = logging.getLogger(__name__)

# Renew an Instagram token once this little of its 60 days is left.
RENEW_WITHIN = timedelta(days=30)
# Meta renews only a token at least a day old.
RENEWABLE_AFTER = timedelta(days=1)

OnExpired = Callable[[Session, ConnectedAccount], None]
SessionFactory = Callable[[], AbstractContextManager[Session]]


@dataclass(frozen=True)
class RefreshRun:
    read: int
    expired: int
    unavailable: int
    # Removed, reconnected or expired after the run listed it: left alone.
    skipped: int = 0


def needs_renewal(connection: ConnectedAccount, now: datetime) -> bool:
    """Whether to renew the token before reading. Pure."""
    if connection.platform == "youtube":
        return True
    expires = connection.token_expires_at
    old_enough = now - connection.connected_at >= RENEWABLE_AFTER
    return old_enough and (expires is None or expires - now <= RENEW_WITHIN)


def refresh_all(
    session_factory: SessionFactory, now: datetime, on_expired: OnExpired
) -> RefreshRun:
    """One run of the job: every active connection, each in its own transactions."""
    if not settings.platform_connections_enabled:
        return RefreshRun(read=0, expired=0, unavailable=0, skipped=0)
    with session_factory() as db:
        ids = list(
            db.scalars(
                select(ConnectedAccount.id)
                .where(ConnectedAccount.status == "active")
                .order_by(ConnectedAccount.id)
            ).all()
        )
    outcomes = [refresh_one(session_factory, i, now, on_expired) for i in ids]
    run = RefreshRun(
        read=outcomes.count("read"),
        expired=outcomes.count("expired"),
        unavailable=outcomes.count("unavailable"),
        skipped=outcomes.count("gone"),
    )
    logger.info(
        "connections.refreshed read=%d expired=%d unavailable=%d skipped=%d",
        run.read,
        run.expired,
        run.unavailable,
        run.skipped,
    )
    return run


def refresh_one(
    session_factory: SessionFactory,
    connection_id: uuid.UUID,
    now: datetime,
    on_expired: OnExpired,
) -> str:
    """Renew if due, read the count, store both. 'read', 'expired', 'unavailable' or 'gone'."""
    with session_factory() as db:
        connection = db.get(ConnectedAccount, connection_id)
        if connection is None or connection.status != "active":
            return "gone"
        tokens = tokens_of(connection)
        platform, seen_at = connection.platform, connection.updated_at
        lapsed = (
            connection.token_expires_at is not None
            and connection.token_expires_at <= now
            and platform == "instagram"
        )
        renew = needs_renewal(connection, now)
    if tokens is None or lapsed:
        # The key changed, or a token lapsed: no platform can be asked.
        return _expire(session_factory, connection_id, seen_at, now, on_expired)

    client = platform_clients.get_platform_client(platform)
    try:
        fresh = client.refresh(tokens, now) if renew else tokens
        found = client.profile(fresh)
    except PlatformRefused:
        return _expire(session_factory, connection_id, seen_at, now, on_expired)
    except PlatformUnavailable:
        logger.info("connections.unavailable platform=%s", platform)
        return "unavailable"

    with session_factory() as db:
        connection = _locked_if_unchanged(db, connection_id, seen_at)
        if connection is None:
            return "gone"
        if renew:
            connection.access_token_sealed = vault.seal(
                fresh.access_token,
                token_context(connection.creator_id, platform, b"access:"),
            )
            connection.token_expires_at = fresh.expires_at
        connection.handle = found.handle
        connection.verified_followers = found.followers
        connection.verified_as_of = now if found.followers is not None else None
        connection.updated_at = now
        db.commit()
    return "read"


def _locked_if_unchanged(
    db: Session, connection_id: uuid.UUID, seen_at: datetime
) -> ConnectedAccount | None:
    """The connection under its lock, unless it was reconnected or removed meanwhile."""
    connection = db.scalars(
        select(ConnectedAccount)
        .where(ConnectedAccount.id == connection_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).first()
    if connection is None or connection.updated_at != seen_at:
        db.rollback()
        return None
    return connection


def _expire(
    session_factory: SessionFactory,
    connection_id: uuid.UUID,
    seen_at: datetime,
    now: datetime,
    on_expired: OnExpired,
) -> str:
    with session_factory() as db:
        connection = _locked_if_unchanged(db, connection_id, seen_at)
        if connection is None:
            return "gone"
        connection.status = "expired"
        connection.updated_at = now
        on_expired(db, connection)
        db.commit()
    logger.info("connections.expired platform=%s", connection.platform)
    return "expired"
