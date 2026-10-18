"""A person's passkeys: adding, naming, removing, passkey-only sign-in, and a reset (item 79, D-113).

The checks are in `auth.passkeys`; here, in `me`, because each change tells
the owner, and notifications sit a layer above auth (D-099).

Threat model (security.md section 4):

- **A SIM swapper adding their own passkey**, to then pass every check a
  passkey guards: the first passkey needs a phone code and a login at least
  a week old (D-109), which a SIM swapper's never is, unless the login is the
  account's very first, when there is no earlier owner to protect. Every
  later passkey needs one of the account's passkeys.
- **A SIM swapper removing the owner's passkeys**: removing one needs a
  passkey. Someone who lost them all starts a reset with the number and a
  code (`request_reset`); it waits PASSKEY_RESET_WAIT, the owner is told, and
  any passkey sign-in before then cancels it.
- **A SIM swapper logging in at all**: with "passkey only" on, a phone code
  no longer logs in (`auth.service.verify_otp`); it can only start a reset.
  Turning it on or off needs a passkey, and the owner is told.
- **Someone guessing at keys**: every answer is checked by `fido2` against
  our domain, our origins and a single-use challenge; see `auth.passkeys`.
"""

import logging
import uuid
from collections.abc import Callable, Mapping
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import delete, exists, func, select
from sqlalchemy.orm import Session

from app.core.export import ExportedSection, allow, build_section
from app.modules.auth import login_age, passkeys
from app.modules.auth import service as login
from app.modules.auth import step_up_service as step_ups
from app.modules.auth.exceptions import (
    NoPasskeyToReset,
    PasskeyNeededFirst,
    PasskeyNotFound,
    RoleNotAllowed,
)
from app.modules.auth.models.account import Account
from app.modules.auth.models.auth_session import AuthSession
from app.modules.auth.models.passkey import PASSKEY_RESET_WAIT, Passkey, PasskeyReset
from app.modules.notifications import service as notifications

logger = logging.getLogger(__name__)

EXPORTED_TABLES = frozenset({"passkey", "passkey_reset"})
# What a person can recognise each key by; never the public key or the
# credential's id, which mean nothing to them.
PASSKEY_EXPORT_FIELDS = allow(
    "id",
    "name",
    "aaguid",
    "backup_eligible",
    "backup_state",
    "last_used_at",
    "created_at",
    "updated_at",
)
RESET_EXPORT_FIELDS = allow("requested_at", "takes_effect_at", "created_at", "updated_at")
PASSKEY_ROLES = ("brand", "creator")


@dataclass(frozen=True)
class PasskeyState:
    """An account's passkeys, whether only they sign in, and a reset waiting."""

    passkeys: list[Passkey]
    passkey_only: bool
    reset: PasskeyReset | None


@dataclass(frozen=True)
class ResetRun:
    """What one run of the job did with resets."""

    reset: int
    cancelled: int
    challenges_removed: int


def ensure_may_have_passkeys(account: Account) -> None:
    """Raises RoleNotAllowed for an admin, whose passkeys wait for their web page."""
    if account.role not in PASSKEY_ROLES:
        raise RoleNotAllowed("Admins sign in with their authenticator for now.")


def state_of(db: Session, account: Account) -> PasskeyState:
    """The account's passkeys, its passkey-only setting and any reset waiting.

    A reset that a passkey sign-in has cancelled is not shown; the job
    removes it and tells the owner.
    """
    reset = db.scalars(
        select(PasskeyReset).where(PasskeyReset.account_id == account.id)
    ).first()
    if reset is not None and _cancelled_by_a_sign_in(db, reset):
        reset = None
    return PasskeyState(
        passkeys=passkeys.for_account(db, account.id),
        passkey_only=account.passkey_only,
        reset=reset,
    )


def registration_options(db: Session, account: Account, now: datetime) -> dict[str, Any]:
    """What the phone needs to make a passkey. Commits. Raises RoleNotAllowed, PasskeysNotOpen."""
    ensure_may_have_passkeys(account)
    return passkeys.registration_options(db, account, now)


def add(
    db: Session,
    account: Account,
    credential: Mapping[str, Any],
    name: str,
    step_up_code: str | None,
    authenticated_at: datetime | None,
    now: datetime,
) -> Passkey:
    """Keep a new passkey, proven by a code for `add_passkey`. Commits.

    The first passkey needs a phone code and a login at least a week old,
    unless this login is the account's first; every later one needs a
    passkey's grant (`step_up_service.consume` takes only that once one
    exists). The owner is told. Raises RoleNotAllowed, LoginTooRecent, what
    step_up_service.consume raises, and what passkeys.add raises.
    """
    ensure_may_have_passkeys(account)
    if not passkeys.has_any(db, account.id) and not _first_login(
        db, account, authenticated_at
    ):
        login_age.ensure_established(authenticated_at, now)
    step_ups.consume(db, account, "add_passkey", "", step_up_code, now)
    passkey = passkeys.add(db, account, credential, name, now)
    notifications.record(
        db,
        account_id=account.id,
        notification_type="passkey_added",
        now=now,
        details={"passkey_id": str(passkey.id), "name": passkey.name},
    )
    db.commit()
    return passkey


def rename(
    db: Session, account: Account, passkey_id: uuid.UUID, name: str, now: datetime
) -> Passkey:
    """Give one of the account's passkeys a new name. Commits. Raises PasskeyNotFound."""
    passkey = _own(db, account, passkey_id)
    passkey.name = name
    passkey.updated_at = now
    db.commit()
    return passkey


def remove(
    db: Session,
    account: Account,
    passkey_id: uuid.UUID,
    step_up_code: str | None,
    now: datetime,
) -> None:
    """Remove one passkey, proven by a passkey's grant for that one. Commits.

    Removing the last also turns passkey-only sign-in off, since nothing
    could sign in then. The owner is told. Raises PasskeyNotFound and what
    step_up_service.consume raises.
    """
    _own(db, account, passkey_id)
    step_ups.consume(db, account, "remove_passkey", str(passkey_id), step_up_code, now)
    # The key, then the account (see _settle for why this order and kind).
    db.execute(select(Passkey.id).where(Passkey.id == passkey_id).with_for_update())
    db.execute(
        select(Account.id).where(Account.id == account.id).with_for_update(key_share=True)
    )
    db.execute(delete(Passkey).where(Passkey.id == passkey_id))
    if not passkeys.has_any(db, account.id) and account.passkey_only:
        account.passkey_only = False
        account.updated_at = now
    notifications.record(
        db,
        account_id=account.id,
        notification_type="passkey_removed",
        now=now,
        details={"count": 1, "reason": "removed"},
    )
    db.commit()


def set_passkey_only(
    db: Session,
    account: Account,
    enabled: bool,
    step_up_code: str | None,
    now: datetime,
) -> Account:
    """Turn passkey-only sign-in on or off, with a passkey's grant. Commits.

    The grant is for exactly "on" or "off". Raises PasskeyNeededFirst (no
    passkey yet), and what step_up_service.consume raises.
    """
    ensure_may_have_passkeys(account)
    if not passkeys.has_any(db, account.id):
        raise PasskeyNeededFirst()
    value = "on" if enabled else "off"
    step_ups.consume(db, account, "passkey_only", value, step_up_code, now)
    if account.passkey_only != enabled:
        account.passkey_only = enabled
        account.updated_at = now
        notifications.record(
            db,
            account_id=account.id,
            notification_type="passkey_only_changed",
            now=now,
            details={"passkey_only": enabled},
        )
    db.commit()
    return account


def request_reset(db: Session, phone: str, code: str, now: datetime) -> PasskeyReset:
    """Start removing every passkey of the account on `phone`, which lost them. Commits.

    Proven by a login code for the number, used up here. It takes effect
    PASSKEY_RESET_WAIT later, unless a passkey signs in before then; the
    owner is told. One already waiting is kept, never restarted, so asking
    again cannot push the owner's chance to cancel further away, nor bring
    the reset nearer. Raises what service.check_phone_code raises, and
    NoPasskeyToReset (no account on the number, or none with a passkey;
    told only to someone whose code was right).
    """
    challenge = login.check_phone_code(db, phone, code, now)
    account = db.scalars(select(Account).where(Account.phone == phone)).first()
    if account is None or not passkeys.has_any(db, account.id):
        db.rollback()
        raise NoPasskeyToReset()
    challenge.consumed_at = now
    reset = db.scalars(
        select(PasskeyReset)
        .where(PasskeyReset.account_id == account.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).first()
    if reset is not None and not _cancelled_by_a_sign_in(db, reset):
        db.commit()
        return reset
    if reset is not None:
        db.delete(reset)
        db.flush()
    reset = PasskeyReset(
        account_id=account.id,
        requested_at=now,
        takes_effect_at=now + PASSKEY_RESET_WAIT,
        created_at=now,
        updated_at=now,
    )
    db.add(reset)
    notifications.record(
        db,
        account_id=account.id,
        notification_type="passkey_reset_requested",
        now=now,
        details={"takes_effect_at": reset.takes_effect_at.isoformat()},
    )
    db.commit()
    return reset


def run_resets(
    session_factory: Callable[[], AbstractContextManager[Session]], now: datetime
) -> ResetRun:
    """One run of the job: make or cancel every reset that is due or cancelled.

    A reset a passkey sign-in has cancelled is removed and the owner told;
    one whose wait is over removes every passkey, turns passkey-only off,
    and tells the owner. Each in its own transaction. Old challenges are
    tidied too.
    """
    with session_factory() as db:
        ids = list(db.scalars(select(PasskeyReset.id).order_by(PasskeyReset.id)).all())
    made = cancelled = 0
    for reset_id in ids:
        with session_factory() as db:
            outcome = _settle(db, reset_id, now)
        made += outcome == "reset"
        cancelled += outcome == "cancelled"
    with session_factory() as db:
        removed = passkeys.tidy_challenges(db, now)
    run = ResetRun(reset=made, cancelled=cancelled, challenges_removed=removed)
    logger.info(
        "passkey.run reset=%d cancelled=%d challenges_removed=%d",
        run.reset,
        run.cancelled,
        run.challenges_removed,
    )
    return run


def _settle(db: Session, reset_id: uuid.UUID, now: datetime) -> str | None:
    reset = db.scalars(
        select(PasskeyReset)
        .where(PasskeyReset.id == reset_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).first()
    if reset is None:
        db.commit()
        return None
    # Every key locked before asking whether one signed in: a sign-in under
    # way holds its key's lock, so it finishes, and is counted, first. Keys
    # before the account, the order a sign-in takes them in, and the
    # account's lock the kind a sign-in's new session does not wait on (it
    # changes no key column), so the two can never wait on each other.
    db.execute(
        select(Passkey.id).where(Passkey.account_id == reset.account_id).with_for_update()
    )
    account = db.scalars(
        select(Account)
        .where(Account.id == reset.account_id)
        .with_for_update(key_share=True)
    ).one()
    if _cancelled_by_a_sign_in(db, reset):
        db.delete(reset)
        notifications.record(
            db,
            account_id=account.id,
            notification_type="passkey_reset_cancelled",
            now=now,
        )
        db.commit()
        return "cancelled"
    if now < reset.takes_effect_at:
        db.commit()
        return None
    removed = db.execute(delete(Passkey).where(Passkey.account_id == account.id))
    count = int(getattr(removed, "rowcount", 0) or 0)
    account.passkey_only = False
    account.updated_at = now
    db.delete(reset)
    notifications.record(
        db,
        account_id=account.id,
        notification_type="passkey_removed",
        now=now,
        details={"count": count, "reason": "reset"},
    )
    db.commit()
    return "reset"


def _cancelled_by_a_sign_in(db: Session, reset: PasskeyReset) -> bool:
    """Whether a passkey has signed in, or approved a change, after the reset was asked.

    Strictly after: a use in the same instant as the request came before it.
    """
    return bool(
        db.scalar(
            select(
                exists().where(
                    Passkey.account_id == reset.account_id,
                    Passkey.last_used_at > reset.requested_at,
                )
            )
        )
    )


def _first_login(
    db: Session, account: Account, authenticated_at: datetime | None
) -> bool:
    """Whether this login is the account's first: no session began before it.

    `auth_time` is rounded up to the second, so a session from a second
    before it still counts as this login's own.
    """
    if authenticated_at is None:
        return False
    earlier = db.scalar(
        select(func.count()).where(
            AuthSession.account_id == account.id,
            AuthSession.created_at < authenticated_at - timedelta(seconds=1),
        )
    )
    return earlier == 0


def ensure_own(db: Session, account: Account, passkey_id: uuid.UUID) -> None:
    """Raises PasskeyNotFound unless the passkey is this account's."""
    _own(db, account, passkey_id)


def _own(db: Session, account: Account, passkey_id: uuid.UUID) -> Passkey:
    passkey = db.scalars(
        select(Passkey).where(Passkey.id == passkey_id, Passkey.account_id == account.id)
    ).first()
    if passkey is None:
        raise PasskeyNotFound()
    return passkey


def export_for_account(db: Session, account_id: uuid.UUID) -> list[ExportedSection]:
    """The account's passkeys, as it can recognise them, and any reset waiting."""
    keys = passkeys.for_account(db, account_id)
    reset = db.scalars(
        select(PasskeyReset).where(PasskeyReset.account_id == account_id)
    ).first()
    return [
        build_section(
            "passkeys",
            table="passkey",
            purpose=(
                "The passkeys you added: their names, which kind of authenticator "
                "made each (its make, never you), whether it syncs to your other "
                "devices, and when each was last used. We hold only each key's "
                "public half; your fingerprint or face never leaves your phone."
            ),
            objects=keys,
            fields=PASSKEY_EXPORT_FIELDS,
        ),
        build_section(
            "passkey_reset",
            table="passkey_reset",
            purpose=(
                "A reset of your passkeys asked for with your number, and when it "
                "takes effect: it waits 7 days, and any sign-in with a passkey "
                "before then cancels it."
            ),
            objects=[reset] if reset is not None else [],
            fields=RESET_EXPORT_FIELDS,
        ),
    ]
