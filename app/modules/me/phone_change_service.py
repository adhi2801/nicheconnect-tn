"""Changing the phone number an account logs in with (item 80, D-108).

The phone is the whole login, so moving the account onto another number is
binding a new authenticator (NIST SP 800-63B-4 sections 3.1.3.3 and
4.1.2.1): it needs proof of both numbers, and the owner is told. Here, in
`me` rather than `auth`, because the owner is told and notifications sit a
layer above auth (D-099). The table and what login needs of it are in auth
(`models.account_phone_change`, `phone_changes`).

Threat model (security.md section 4):

- **A stolen session** cannot start a change: it needs a code from the
  current number, asked for to move onto this exact new number
  (`step_up_service`, action `change_phone`), and a login code from the new
  number. Both caps per phone apply, for sending and for guessing.
- **A SIM swap of the current number** gets the first code, so it can start
  one. It cannot make it stick: the change waits PHONE_CHANGE_WAIT, the old
  number still logs in meanwhile, and the owner, once their carrier gives
  the number back, logs in and cancels with no code. The owner is told by a
  notification nobody can mute, and it is first on their attention list.
  What is left is an owner who never opens the app for those 72 hours:
  nothing yet reaches them outside it (E1).
- **A recycled number** (TRAI: reissued after 90 days): once the change is
  made the old number is let go, so its next holder logging in gets a new
  account, never this one.
- **The new number taken meanwhile**: login refuses a new account on a
  number some account is waiting for, and the move checks again under
  both numbers' locks; if it is taken anyway (an admin made by the script),
  the change is dropped and the owner told.
- **Learning who has an account**: "already on an account" is said only
  after the new number's code was right, so only its holder learns it.

When it is made, every session ends, the one that asked included, so the
new number is proven once more, by logging in with it, at the moment it
takes over. The pending row is deleted when the change is made or
cancelled: no past number is kept.
"""

import logging
import uuid
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from sqlalchemy import exists, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.export import ExportedSection, allow, build_section
from app.modules.auth import phone_changes
from app.modules.auth import service as login
from app.modules.auth import step_up_service as step_ups
from app.modules.auth.exceptions import (
    PhoneChangeTakingEffect,
    PhoneInUse,
    PhoneUnchanged,
    RoleNotAllowed,
    StepUpRequired,
)
from app.modules.auth.models.account import Account
from app.modules.auth.models.account_phone_change import (
    PHONE_CHANGE_WAIT,
    AccountPhoneChange,
)
from app.modules.notifications import service as notifications

logger = logging.getLogger(__name__)

EXPORTED_TABLES = frozenset({"account_phone_change"})
EXPORT_FIELDS = allow(
    "new_phone", "requested_at", "takes_effect_at", "created_at", "updated_at"
)
# An admin's number changes only through scripts/make_admin.py, as their
# authenticator does: no route, so no help desk to talk round (D-105).
CHANGE_ROLES = ("brand", "creator")
# Changes made in one run of the job; any more are made a minute later.
MAX_CHANGES_PER_RUN = 50

Outcome = Literal["made", "dropped"]


@dataclass(frozen=True)
class PhoneChangeState:
    """The number an account logs in with, and a new one waiting, if any."""

    phone: str
    waiting: AccountPhoneChange | None


@dataclass(frozen=True)
class ChangeRun:
    """What one run of the job did."""

    due: int
    made: int
    dropped: int


def ensure_new_phone(account: Account, new_phone: str) -> None:
    """Refuse a change this account may not ask for, before any code is sent.

    Raises RoleNotAllowed (an admin) and PhoneUnchanged (its own number).
    """
    if account.role not in CHANGE_ROLES:
        raise RoleNotAllowed("An admin's number is changed by the founders' script.")
    if new_phone == account.phone:
        raise PhoneUnchanged()


def get_for_account(db: Session, account: Account) -> PhoneChangeState:
    """The account's number, and a new one still waiting to replace it."""
    waiting = db.scalars(
        select(AccountPhoneChange)
        .where(AccountPhoneChange.account_id == account.id)
        .execution_options(populate_existing=True)
    ).first()
    return PhoneChangeState(phone=account.phone, waiting=waiting)


def request_change(
    db: Session,
    account: Account,
    new_phone: str,
    new_phone_code: str,
    step_up_code: str | None,
    now: datetime,
) -> PhoneChangeState:
    """Start moving the account onto `new_phone`, which takes over in 72 hours.

    Needs both codes: `step_up_code` from the current number, asked for to
    move onto exactly `new_phone`, and `new_phone_code`, a login code sent to
    `new_phone`, which this uses up so it cannot also log anyone in. A change
    already waiting is replaced, and its 72 hours start again.

    Both numbers are locked first, in sorted order, so a login, a code and a
    move on the same numbers run one at a time. The new number's code is
    checked before the current number's: a wrong one commits only its own
    attempt, never the other code's use.

    Raises RoleNotAllowed, PhoneUnchanged, StepUpRequired,
    PhoneChangeTakingEffect (the change waiting is past its 72 hours),
    PhoneInUse (the new number has an account, or another is waiting for
    it), what service.check_phone_code raises for the new number's code, and
    what step_up_service.consume raises for the current number's.
    """
    ensure_new_phone(account, new_phone)
    if step_up_code is None:
        raise StepUpRequired()
    login.lock_phones(db, account.phone, new_phone)
    waiting = _locked_change(db, account.id)
    if waiting is not None and phone_changes.is_due(waiting, now):
        db.rollback()
        raise PhoneChangeTakingEffect()

    new_number = login.check_phone_code(db, new_phone, new_phone_code, now)
    step_ups.consume(db, account, "change_phone", new_phone, step_up_code, now)
    if db.scalar(select(exists().where(Account.phone == new_phone))):
        db.rollback()
        raise PhoneInUse()

    new_number.consumed_at = now
    takes_effect_at = now + PHONE_CHANGE_WAIT
    values = {
        "new_phone": new_phone,
        "requested_at": now,
        "takes_effect_at": takes_effect_at,
        "updated_at": now,
    }
    try:
        db.execute(
            insert(AccountPhoneChange)
            .values(account_id=account.id, created_at=now, **values)
            .on_conflict_do_update(
                index_elements=[AccountPhoneChange.account_id], set_=values
            )
        )
    except IntegrityError:
        # Another account is already waiting for this number: the database's
        # own rule (uq_account_phone_change_new_phone) is the check.
        db.rollback()
        raise PhoneInUse() from None
    notifications.record(
        db,
        account_id=account.id,
        notification_type="phone_change_requested",
        now=now,
        details={"takes_effect_at": takes_effect_at.isoformat()},
    )
    db.commit()
    return get_for_account(db, account)


def cancel(db: Session, account: Account, now: datetime) -> None:
    """Drop a new number still waiting, so the account keeps the one it has.

    No code is asked for: cancelling only keeps the number the account
    already logs in with, and the owner must be able to do it from any of
    their sessions, even while someone else holds their number. Nothing
    waiting is fine, and safe to repeat. Raises PhoneChangeTakingEffect once
    the 72 hours are over.
    """
    waiting = _locked_change(db, account.id)
    if waiting is None:
        # Nothing written: this only ends the transaction and its lock.
        db.commit()
        return
    if phone_changes.is_due(waiting, now):
        db.rollback()
        raise PhoneChangeTakingEffect()
    db.delete(waiting)
    notifications.record(
        db, account_id=account.id, notification_type="phone_change_cancelled", now=now
    )
    db.commit()


def run_changes(
    session_factory: Callable[[], AbstractContextManager[Session]], now: datetime
) -> ChangeRun:
    """One run of the job: make every change whose 72 hours are over.

    Each in its own transaction, so one that fails leaves the rest made.
    """
    with session_factory() as db:
        due = list(
            db.scalars(
                select(AccountPhoneChange.id)
                .where(AccountPhoneChange.takes_effect_at <= now)
                .order_by(AccountPhoneChange.takes_effect_at, AccountPhoneChange.id)
                .limit(MAX_CHANGES_PER_RUN)
            ).all()
        )
    outcomes: list[Outcome | None] = []
    for change_id in due:
        with session_factory() as db:
            outcomes.append(make_change(db, change_id, now))
    run = ChangeRun(
        due=len(due), made=outcomes.count("made"), dropped=outcomes.count("dropped")
    )
    logger.info(
        "phone_change.run due=%d made=%d dropped=%d", run.due, run.made, run.dropped
    )
    return run


def make_change(db: Session, change_id: uuid.UUID, now: datetime) -> Outcome | None:
    """Move one account onto its new number, if its 72 hours are over. Commits.

    Both numbers are locked first, as for asking, then the change and the
    account, and the change is read again under the locks: one already made
    by another run, or not yet due, is left alone (None). Once due, a change
    can be neither cancelled nor replaced, so its numbers cannot change
    between the first read and the locks.
    If the new number now has an account, the change is dropped and the
    owner told ("dropped"). Otherwise the account takes the new number,
    every session ends and every push token is forgotten, and the owner is
    told when they next log in ("made"). The old number is let go.
    """
    found = db.execute(
        select(Account.phone, AccountPhoneChange.new_phone)
        .join(Account, Account.id == AccountPhoneChange.account_id)
        .where(AccountPhoneChange.id == change_id)
    ).first()
    if found is None:
        db.commit()
        return None
    old_phone, new_phone = found
    login.lock_phones(db, old_phone, new_phone)
    change = db.scalars(
        select(AccountPhoneChange)
        .where(AccountPhoneChange.id == change_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).first()
    if change is None or not phone_changes.is_due(change, now):
        db.commit()
        return None
    account = db.scalars(
        select(Account)
        .where(Account.id == change.account_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).one()

    db.delete(change)
    if db.scalar(select(exists().where(Account.phone == new_phone))):
        notifications.record(
            db, account_id=account.id, notification_type="phone_change_failed", now=now
        )
        db.commit()
        logger.warning("phone_change.dropped change_id=%s", change_id)
        return "dropped"

    account.phone = new_phone
    account.updated_at = now
    ended = login.logout_all_sessions(db, account.id, now)
    notifications.record(
        db,
        account_id=account.id,
        notification_type="phone_changed",
        now=now,
        details={"sessions_ended": ended},
    )
    db.commit()
    return "made"


def export_for_account(db: Session, account_id: uuid.UUID) -> list[ExportedSection]:
    """A new number the account is waiting to move onto, if any."""
    waiting = db.scalars(
        select(AccountPhoneChange).where(AccountPhoneChange.account_id == account_id)
    ).first()
    return [
        build_section(
            "phone_change",
            table="account_phone_change",
            purpose=(
                "A new phone number you asked to log in with, and when it "
                "takes over: a new number waits 72 hours, so someone who took "
                "over your current number cannot move your account before you "
                "notice. Until then you log in with your current number. Once "
                "the change is made or cancelled this is deleted; we keep no "
                "earlier numbers."
            ),
            objects=[waiting] if waiting is not None else [],
            fields=EXPORT_FIELDS,
        )
    ]


def _locked_change(db: Session, account_id: uuid.UUID) -> AccountPhoneChange | None:
    return db.scalars(
        select(AccountPhoneChange)
        .where(AccountPhoneChange.account_id == account_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).first()
