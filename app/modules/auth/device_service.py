"""Registering the phones that receive push notifications (item 9, D-095).

The apps call `register` on every start and whenever Firebase or Apple hands
them a new token; it is safe to repeat. Three rules, each with a reason:

1. **One owner per token.** A token registered by a second account moves to
   it. A phone handed on keeps its token, and the last person's deals and
   payments must stop appearing on it.
2. **At most `MAX_DEVICES_PER_ACCOUNT` per account**, keeping the most
   recently seen. Every reinstall makes a new token, and the old ones lead
   nowhere. The account's row is locked first, so two registrations at once
   cannot both see room for one more.
3. **Gone when the person leaves.** Each token remembers the session that
   registered it, and ending that session removes it, however it ends: a
   logout, ending it from another device, logging out everywhere, a moved
   phone number, a suspension (D-116). A token registered before sessions
   were named goes when its phone logs out with it, or everywhere.

A token is personal data: never logged, never in a URL, never in a response.
"""

import uuid
from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.export import ExportedSection, allow, build_section
from app.modules.auth.exceptions import DeviceNotFound, InvalidToken
from app.modules.auth.models.account import Account
from app.modules.auth.models.auth_session import AuthSession
from app.modules.auth.models.device_token import MAX_DEVICES_PER_ACCOUNT, DeviceToken

EXPORTED_TABLES = frozenset({"device_token"})
# The token itself is never exported (app/core/export.py refuses the name): it
# is an address only our push sender can use, and the platform and dates say
# all a person needs to recognise their own phones.
EXPORT_FIELDS = allow(
    "id", "platform", "app_version", "session_id", "last_seen_at", "created_at"
)


def register(
    db: Session,
    account_id: uuid.UUID,
    *,
    token: str,
    platform: str,
    app_version: str | None,
    now: datetime,
    session_id: uuid.UUID | None = None,
) -> DeviceToken:
    """Record this phone for this account and session, or refresh it. Commits.

    One `INSERT ... ON CONFLICT`, so a token registered by two accounts at
    once ends with exactly one of them, never an error. The account's row
    is locked first, as everything that ends a session locks it, so a
    session ended while this waited is seen, and its phone is refused
    rather than registered to a session that no longer exists (D-116).
    Raises InvalidToken for that.
    """
    db.execute(select(Account.id).where(Account.id == account_id).with_for_update())
    if session_id is not None and not _session_live(db, account_id, session_id):
        db.rollback()
        raise InvalidToken()
    device = db.scalars(
        insert(DeviceToken)
        .values(
            account_id=account_id,
            platform=platform,
            token=token,
            app_version=app_version,
            session_id=session_id,
            last_seen_at=now,
            created_at=now,
            updated_at=now,
        )
        .on_conflict_do_update(
            index_elements=[DeviceToken.token],
            set_={
                "account_id": account_id,
                "platform": platform,
                "app_version": app_version,
                "session_id": session_id,
                "last_seen_at": now,
                "updated_at": now,
            },
        )
        .returning(DeviceToken),
        execution_options={"populate_existing": True},
    ).one()
    _keep_most_recent(db, account_id)
    db.commit()
    return device


def _session_live(db: Session, account_id: uuid.UUID, session_id: uuid.UUID) -> bool:
    """Whether the session has a row not yet revoked, as every request checks."""
    found = db.scalar(
        select(AuthSession.id)
        .where(
            AuthSession.account_id == account_id,
            AuthSession.family_id == session_id,
            AuthSession.revoked_at.is_(None),
        )
        .limit(1)
    )
    return found is not None


def forget_session(
    db: Session, account_id: uuid.UUID, session_id: uuid.UUID | None = None
) -> None:
    """When sessions end: the phones they registered. Never commits.

    One session's (`session_id`), or, with none given, every phone of the
    account, since every session of it ended.
    """
    statement = delete(DeviceToken).where(DeviceToken.account_id == account_id)
    if session_id is not None:
        statement = statement.where(DeviceToken.session_id == session_id)
    db.execute(statement)


def _keep_most_recent(db: Session, account_id: uuid.UUID) -> None:
    """Forget all but the account's most recently seen phones."""
    kept = (
        select(DeviceToken.id)
        .where(DeviceToken.account_id == account_id)
        .order_by(DeviceToken.last_seen_at.desc(), DeviceToken.id.desc())
        .limit(MAX_DEVICES_PER_ACCOUNT)
    )
    db.execute(
        delete(DeviceToken).where(
            DeviceToken.account_id == account_id, DeviceToken.id.not_in(kept)
        )
    )


def remove(db: Session, account_id: uuid.UUID, device_id: uuid.UUID) -> None:
    """Stop pushing to one of this account's phones. Commits.

    Raises DeviceNotFound for an unknown id or another account's device.
    """
    removed = db.execute(
        delete(DeviceToken)
        .where(DeviceToken.id == device_id, DeviceToken.account_id == account_id)
        .returning(DeviceToken.id)
    ).first()
    if removed is None:
        db.rollback()
        raise DeviceNotFound()
    db.commit()


def forget_token(db: Session, account_id: uuid.UUID, token: str) -> None:
    """On logging out of a phone: its token, if it is this account's.

    Never commits and never says whether it existed: logout looks the same
    whatever it is given.
    """
    db.execute(
        delete(DeviceToken).where(
            DeviceToken.token == token, DeviceToken.account_id == account_id
        )
    )


def forget_all(db: Session, account_id: uuid.UUID) -> None:
    """On logging out everywhere: every phone of this account. Never commits."""
    db.execute(delete(DeviceToken).where(DeviceToken.account_id == account_id))


def export_for_account(db: Session, account_id: uuid.UUID) -> list[ExportedSection]:
    rows = list(
        db.scalars(
            select(DeviceToken)
            .where(DeviceToken.account_id == account_id)
            .order_by(DeviceToken.last_seen_at.desc())
        ).all()
    )
    return [
        build_section(
            "devices",
            table="device_token",
            purpose=(
                "The phones registered to receive push notifications for you: "
                "which kind of phone, which app version, and when each last "
                "checked in. The address the phone gave us is not included; "
                "only our notification sender can use it."
            ),
            objects=rows,
            fields=EXPORT_FIELDS,
        )
    ]
