"""Deleting your own account (item 6, D-122).

Apple (App Review guideline 5.1.1(v)) and Google Play reject apps that let
people make an account but not delete it in the app, and DPDP Rule 8 asks
for erasure. Here, in `me`, because deleting reaches every module.

How it works (D-122, choices 1A, 2A and 3A):

1. The owner asks (`request_deletion`), with a step-up code for
   `delete_account`. It is refused while any deal of theirs is unfinished
   (`deal_memo.unfinished`), so a brand cannot leave to avoid paying, and
   nobody loses the person they are working with mid-deal.
2. It takes effect 30 days later. Until then the account works as before,
   the owner is told by a notice nobody can mute, it leads their attention
   list, and they cancel at any time with no code (`cancel`).
3. Then the job erases it (`run_deletions`): what no law asks us to keep is
   deleted, the account and profile are emptied, and what a law may require
   is kept (`account_deletion_registry`). A deal begun during the 30 days
   holds it, with the owner told once, until that deal is finished.

Threat model (security.md section 4):

- **A stolen session** cannot ask: it needs a code from the phone (or the
  passkey, once there is one).
- **A SIM swapper** gets the code, but the 30 days are the owner's: they
  are told in the app, it is first on their attention list, and any of
  their sessions cancels it, as Google and Instagram give a month. What is
  left is an owner who never opens the app for 30 days (E1).
- **A brand leaving to avoid paying**: refused while the deal is unpaid,
  unconfirmed or disputed, and held at the end if one began meanwhile.
- **Griefing a deletion**: the placeholders that replace a handle or an
  email are random (`auth.erasure`), so nobody can take one in advance and
  make the erasure fail.
- **A request at the moment of erasure**: the erasure takes the phone's
  lock, then the profile, campaigns and applications, then the account's
  row for update, in the order every other path takes them (`erase`). A
  login, a memo or an invitation lands wholly before it or finds the
  person gone; an insert pointing at the account waits for it.
"""

import logging
import uuid
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from app.core.storage import FileStore
from app.modules.auth import erasure
from app.modules.auth import service as login
from app.modules.auth import step_up_service as step_ups
from app.modules.auth.exceptions import RoleNotAllowed
from app.modules.auth.models.account import Account
from app.modules.auth.models.brand import Brand
from app.modules.auth.models.creator import Creator
from app.modules.campaigns import departure_service as departures
from app.modules.deal_memo.unfinished import unfinished_deals
from app.modules.matching import service as matching
from app.modules.me import data_export_service as data_exports
from app.modules.me.account_deletion_registry import KEPT, KeptKind
from app.modules.me.exceptions import DeletionAlreadyRequested, DeletionHeldByDeals
from app.modules.notifications import service as notifications
from app.modules.notifications.models import Notification
from app.modules.payment_status import upi_service as upi
from app.modules.profiles import brand_domain_service as brand_domains
from app.modules.profiles import rate_card_service as rate_cards
from app.modules.safety import block_service as blocks

logger = logging.getLogger(__name__)

# 30 days, cancelled by the owner at any time (D-122, choice 2A): Google
# and Instagram give a month. The database holds the same number
# (ck_account_deletion_takes_effect_thirty_days_after).
DELETION_WAIT = timedelta(days=30)
# An admin account is removed only by the founders, never from the app.
DELETION_ROLES = ("brand", "creator")

DeletionStatus = Literal["none", "waiting", "held"]
Outcome = Literal["erased", "held", "waiting_for_export"]


@dataclass(frozen=True)
class DeletionState:
    """Where the account's deletion stands, and what would hold or survive it."""

    status: DeletionStatus
    requested_at: datetime | None
    takes_effect_at: datetime | None
    unfinished_deal_ids: list[uuid.UUID]
    kept: tuple[KeptKind, ...]


@dataclass(frozen=True)
class DeletionRun:
    """What one run of the job did."""

    due: int
    erased: int
    held: int
    waiting_for_export: int


def _profile_ids(db: Session, account: Account) -> dict[str, uuid.UUID]:
    if account.role == "brand":
        brand_id = db.scalar(select(Brand.id).where(Brand.account_id == account.id))
        return {} if brand_id is None else {"brand_id": brand_id}
    if account.role == "creator":
        creator_id = db.scalar(select(Creator.id).where(Creator.account_id == account.id))
        return {} if creator_id is None else {"creator_id": creator_id}
    return {}


def unfinished_for(db: Session, account: Account, now: datetime) -> list[uuid.UUID]:
    """The ids of the account's deals that would hold its deletion."""
    return unfinished_deals(db, now, **_profile_ids(db, account))


def get_state(db: Session, account: Account, now: datetime) -> DeletionState:
    """The account's deletion, if asked for, and the deals that would hold it."""
    takes_effect_at = account.deletion_takes_effect_at
    status: DeletionStatus = "none"
    if takes_effect_at is not None:
        status = "held" if takes_effect_at <= now else "waiting"
    return DeletionState(
        status=status,
        requested_at=account.deletion_requested_at,
        takes_effect_at=takes_effect_at,
        unfinished_deal_ids=unfinished_for(db, account, now),
        kept=KEPT,
    )


def ensure_may_request(db: Session, account: Account, now: datetime) -> None:
    """Refuse a deletion that would be refused anyway, before any code is sent.

    Raises RoleNotAllowed (an admin), DeletionAlreadyRequested and
    DeletionHeldByDeals.
    """
    if account.role not in DELETION_ROLES:
        raise RoleNotAllowed("An admin account is removed by the founders.")
    if account.deletion_requested_at is not None:
        raise DeletionAlreadyRequested()
    unfinished = unfinished_for(db, account, now)
    if unfinished:
        raise DeletionHeldByDeals(len(unfinished))


def request_deletion(
    db: Session, account: Account, step_up_code: str | None, now: datetime
) -> DeletionState:
    """Ask for the account to be deleted 30 days from now. Commits.

    The code is spent first (`step_up_service.consume`, action
    `delete_account`); the account's row is then locked and read again, so
    two requests at once make one deletion and the other is refused.
    Raises what ensure_may_request raises, StepUpRequired and what
    step_up_service.consume raises.
    """
    ensure_may_request(db, account, now)
    step_ups.consume(db, account, "delete_account", "", step_up_code, now)
    _lock(db, account)
    try:
        ensure_may_request(db, account, now)
    except DeletionAlreadyRequested, DeletionHeldByDeals:
        db.rollback()
        raise
    takes_effect_at = now + DELETION_WAIT
    account.deletion_requested_at = now
    account.deletion_takes_effect_at = takes_effect_at
    account.updated_at = now
    notifications.record(
        db,
        account_id=account.id,
        notification_type="deletion_requested",
        now=now,
        details={"takes_effect_at": takes_effect_at.isoformat()},
    )
    db.commit()
    return get_state(db, account, now)


def cancel(db: Session, account: Account, now: datetime) -> None:
    """Keep the account: drop its deletion, waiting or held. Commits.

    No code is asked for: cancelling only keeps what the owner has, and they
    must be able to do it from any session, even while someone else holds
    their number. Nothing asked for is fine, and safe to repeat. Under the
    account's lock, so it lands wholly before the erasure, which then finds
    nothing to do, or after it, when no session is left to ask.
    """
    _lock(db, account)
    if account.deletion_requested_at is None or account.deleted_at is not None:
        # Nothing written: this only ends the transaction and its lock. A
        # deletion already done keeps its dates as history, and cannot be
        # undone; a request in flight at that moment finds it so.
        db.commit()
        return
    account.deletion_requested_at = None
    account.deletion_takes_effect_at = None
    account.updated_at = now
    notifications.record(
        db, account_id=account.id, notification_type="deletion_cancelled", now=now
    )
    db.commit()


def _lock(db: Session, account: Account) -> None:
    # FOR NO KEY UPDATE, as sessions take it (auth.service.lock_sessions_of):
    # it waits for the erasure's FOR UPDATE, and holds up no row that only
    # points at the account.
    db.scalars(
        select(Account)
        .where(Account.id == account.id)
        .with_for_update(key_share=True)
        .execution_options(populate_existing=True)
    ).one()


def run_deletions(
    session_factory: Callable[[], AbstractContextManager[Session]],
    store: FileStore,
    now: datetime,
) -> DeletionRun:
    """One run of the job: erase every account whose 30 days are over.

    Each in its own transactions, so one that fails or is held leaves the
    rest done. Every due account is looked at on every run, the held ones
    too, so none waits behind another; at pilot scale they are a handful.
    """
    with session_factory() as db:
        due = list(
            db.scalars(
                select(Account.id)
                .where(
                    Account.deletion_takes_effect_at <= now,
                    Account.deleted_at.is_(None),
                )
                .order_by(Account.deletion_takes_effect_at, Account.id)
            ).all()
        )
    outcomes = [
        delete_account(session_factory, store, account_id, now) for account_id in due
    ]
    run = DeletionRun(
        due=len(due),
        erased=outcomes.count("erased"),
        held=outcomes.count("held"),
        waiting_for_export=outcomes.count("waiting_for_export"),
    )
    logger.info(
        "account_deletion.run due=%d erased=%d held=%d waiting_for_export=%d",
        run.due,
        run.erased,
        run.held,
        run.waiting_for_export,
    )
    return run


def delete_account(
    session_factory: Callable[[], AbstractContextManager[Session]],
    store: FileStore,
    account_id: uuid.UUID,
    now: datetime,
) -> Outcome | None:
    """Erase one account whose 30 days are over, unless something holds it.

    Its export files are destroyed first, with no transaction open while
    storage is called; then everything else in one transaction.
    """
    data_exports.destroy_files_of(session_factory, store, account_id, now)
    with session_factory() as db:
        return erase(db, account_id, now)


def erase(db: Session, account_id: uuid.UUID, now: datetime) -> Outcome | None:
    """Erase one account in one transaction, if it is still due. Commits.

    Locks, in this order: the phone, as a login does; the profile; its
    campaigns and applications (`campaigns.departure_service`); and the
    account for update, last. Last because everything else that touches
    these rows reaches the account last too, when it inserts a row pointing
    at it: an invitation locks the creator, then adds the creator's notice;
    an application adds to a campaign, then the brand's notice. Locking the
    account first deadlocked with both. Everything is read again under the
    account's lock: one cancelled meanwhile, already erased, or whose
    number changed, is left alone (None), as is an admin, whom only the
    founders remove, even with dates written by hand.

    Held ("held") while any deal of the person is unfinished, the owner
    told once; waits ("waiting_for_export") while an export of theirs is
    being prepared or still has a file, which the next run destroys first.
    """
    found = db.get(Account, account_id)
    if found is None or found.phone is None or found.role not in DELETION_ROLES:
        db.commit()
        return None
    phone = found.phone
    login.lock_phone(db, phone)
    profile = erasure.lock_profile(db, found)
    if isinstance(profile, Brand):
        applications = departures.lock_for_brand(db, profile.id)
    elif isinstance(profile, Creator):
        applications = departures.lock_for_creator(db, profile.id)
    else:
        applications = []
    account = db.scalars(
        select(Account)
        .where(Account.id == account_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).one()
    if (
        account.deleted_at is not None
        or account.deletion_takes_effect_at is None
        or account.deletion_takes_effect_at > now
        or account.phone != phone
    ):
        db.rollback()
        return None

    if isinstance(profile, Brand):
        unfinished = unfinished_deals(db, now, brand_id=profile.id)
    elif isinstance(profile, Creator):
        unfinished = unfinished_deals(db, now, creator_id=profile.id)
    else:
        unfinished = []
    if unfinished:
        _tell_held_once(db, account, len(unfinished), now)
        db.commit()
        logger.info("account_deletion.held account_id=%s", account_id)
        return "held"
    if data_exports.blocks_erasure(db, account.id):
        db.commit()
        return "waiting_for_export"

    if isinstance(profile, Brand):
        departures.end_for_brand(db, profile.id, applications, now)
        brand_domains.erase_for_brand(db, profile.id)
    elif isinstance(profile, Creator):
        departures.end_for_creator(applications, now)
        upi.erase_for_creator(db, profile.id)
        rate_cards.erase_for_creator(db, profile.id)
        matching.erase_for_creator(db, profile.id)
    notifications.erase_for_account(db, account.id)
    blocks.erase_for_account(db, account.id)
    data_exports.erase_for_account(db, account.id)
    erasure.erase_for_account(db, account)
    erasure.empty_identity(db, account, profile, now)
    db.commit()
    logger.info("account_deletion.erased account_id=%s", account_id)
    return "erased"


def _tell_held_once(
    db: Session, account: Account, unfinished: int, now: datetime
) -> None:
    """Tell the owner, once for this request, that a deal holds the deletion."""
    told = db.scalar(
        select(
            exists().where(
                Notification.account_id == account.id,
                Notification.notification_type == "deletion_held_by_deals",
                Notification.created_at >= account.deletion_requested_at,
            )
        )
    )
    if not told:
        notifications.record(
            db,
            account_id=account.id,
            notification_type="deletion_held_by_deals",
            now=now,
            details={"unfinished_deals": unfinished},
        )
