"""The UPI pay link: a creator's UPI ID, and the brand paying it in one tap (D-085).

Today a brand copies an amount and a UPI ID by hand, the most error-prone
step in a deal. The pay link is NPCI's own `upi://pay` deep link: any UPI
app opens it with the payee, the amount and a note filled in, shows the
payee's name as their bank holds it, and asks the brand for its PIN. The
money goes from the brand's bank to the creator's; it never passes through
us (constraint 1), and nothing here could make it.

Threat model (security.md section 4), in short; the whole one is in
docs/decided/PROPOSAL_UPI_PAY_LINK.md:

- Someone else's UPI ID put on a creator: only the signed-in creator sets
  their own, under `/me`.
- A creator's UPI ID seen by the wrong people: only the brand on that deal,
  only while its payment is open (not yet marked paid), and never a phone
  number, which both the API and the database refuse.
- A taken-over account swapping in the attacker's UPI ID before payment:
  - a stolen session cannot set one at all: every set needs a code sent to
    the phone, for that exact ID (item 82, D-107, `auth.step_up_service`);
  - a SIM swap can get that code, but replacing an ID already in effect
    needs a login at least a week old (D-109), and a SIM swapper's is new;
  - even so, a new ID waits 24 hours before brands
    see it, the previous one staying in effect meanwhile; the creator is
    told, sees it on their attention list, and can cancel it without a code;
  - once in effect, the answer says when the ID was set and flags one set
    in the last 24 hours; the brand's UPI app shows the bank's name for the
    payee before the PIN, which is the check that matters, and the brand is
    told to read it.
- A payment above UPI's limit failing at the bank: no link is offered above
  it, and the reason says so.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from urllib.parse import quote

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.export import ExportedSection, allow, build_section
from app.modules.auth import login_age
from app.modules.auth import step_up_service as step_ups
from app.modules.auth.models.account import Account
from app.modules.auth.models.creator import Creator
from app.modules.campaigns.models import Application, Campaign
from app.modules.deal_memo.models import DealMemo
from app.modules.notifications import service as notifications
from app.modules.payment_status.exceptions import (
    PaymentAlreadyMarkedPaid,
    UpiChangeAlreadyInEffect,
    UpiNoticeChanged,
    UpiNotOpenYet,
)
from app.modules.payment_status.models import PaymentStatus
from app.modules.payment_status.upi_change_models import (
    UPI_CHANGE_HOLD,
    CreatorUpiChange,
)
from app.modules.payment_status.upi_holds import (
    UpiInEffect,
    UpiWaiting,
    in_effect,
    waiting,
)
from app.modules.payment_status.upi_models import CreatorUpi

EXPORTED_TABLES = frozenset({"creator_upi", "creator_upi_change"})
EXPORT_FIELDS = allow(
    "upi_id", "consented_at", "notice_version", "created_at", "updated_at"
)
CHANGE_EXPORT_FIELDS = allow(
    "upi_id", "consented_at", "notice_version", "usable_at", "created_at", "updated_at"
)

# UPI between people: at most ₹1 lakh from one bank account in 24 hours,
# across every UPI app (Google Pay's help on UPI limits, read 10 October
# 2026). Above it the transfer would fail at the bank, so no link is offered.
UPI_PERSON_TO_PERSON_LIMIT_PAISE = 1_00_000 * 100
# A UPI ID set this recently is flagged to the brand before it pays.
RECENT_CHANGE = timedelta(hours=24)
# Kept short: UPI apps show the note in a single line.
NOTE_MAX_LENGTH = 50


@dataclass(frozen=True)
class UpiState:
    """A creator's UPI ID as they see it: the one in effect, and one waiting."""

    in_effect: UpiInEffect | None
    waiting: UpiWaiting | None


@dataclass(frozen=True)
class PayDetails:
    payee_name: str
    upi_id: str | None
    amount_paise: int
    pay_link: str | None
    unavailable_reason: str | None
    upi_id_set_at: datetime | None
    upi_id_changed_recently: bool


def _rows(
    db: Session, creator_id: uuid.UUID
) -> tuple[CreatorUpi | None, CreatorUpiChange | None]:
    """The creator's current ID and any change, in one query."""
    current, change = db.execute(
        select(CreatorUpi, CreatorUpiChange)
        .select_from(Creator)
        .outerjoin(CreatorUpi, CreatorUpi.creator_id == Creator.id)
        .outerjoin(CreatorUpiChange, CreatorUpiChange.creator_id == Creator.id)
        .where(Creator.id == creator_id)
        .execution_options(populate_existing=True)
    ).one()
    return current, change


def get_for_creator(db: Session, creator: Creator, now: datetime) -> UpiState:
    """The creator's UPI ID in effect now, and any new one still waiting."""
    current, change = _rows(db, creator.id)
    return UpiState(
        in_effect=in_effect(current, change, now), waiting=waiting(change, now)
    )


def set_for_creator(
    db: Session,
    account: Account,
    creator: Creator,
    upi_id: str,
    notice_version: str,
    step_up_code: str | None,
    authenticated_at: datetime | None,
    now: datetime,
) -> UpiState:
    """Set the creator's UPI ID, with their consent and a code for that exact ID.

    Consent is given again with every change, against the notice in force:
    a creator who read an older notice is sent back to read the new one,
    before any code is spent.

    The ID already in effect is confirmed at once, with its new consent, and
    any other ID still waiting is dropped. A different ID waits
    UPI_CHANGE_HOLD before brands see it (item 82), replacing any other
    still waiting and starting its wait again, and the creator is told.
    Replacing an ID already in effect needs a login at least a week old
    (D-109), checked before any code is spent; a first ID does not.
    The creator's row is locked first, so two changes at once apply in turn.
    Raises UpiNotOpenYet, UpiNoticeChanged, LoginTooRecent, and what
    step_up_service.consume raises.
    """
    if settings.upi_notice_version is None:
        raise UpiNotOpenYet(
            "Its notice is not ready yet. Until then, brands pay you by bank "
            "transfer or by the UPI ID you give them."
        )
    if notice_version != settings.upi_notice_version:
        raise UpiNoticeChanged()
    ensure_may_replace(db, creator.id, upi_id, authenticated_at, now)
    step_ups.consume(db, account, "set_upi_id", upi_id, step_up_code, now)
    db.execute(select(Creator.id).where(Creator.id == creator.id).with_for_update())
    current, change = _fold(db, creator.id, *_rows(db, creator.id), now)

    if current is not None and current.upi_id == upi_id:
        current.consented_at = now
        current.notice_version = notice_version
        current.updated_at = now
        if change is not None:
            db.delete(change)
    else:
        usable_at = now + UPI_CHANGE_HOLD
        values = {
            "upi_id": upi_id,
            "consented_at": now,
            "notice_version": notice_version,
            "usable_at": usable_at,
            "updated_at": now,
        }
        db.execute(
            insert(CreatorUpiChange)
            .values(creator_id=creator.id, created_at=now, **values)
            .on_conflict_do_update(
                index_elements=[CreatorUpiChange.creator_id], set_=values
            )
        )
        notifications.record(
            db,
            account_id=account.id,
            notification_type="upi_change_pending",
            now=now,
            details={"usable_at": usable_at.isoformat()},
        )
    db.commit()
    return get_for_creator(db, creator, now)


def ensure_may_replace(
    db: Session,
    creator_id: uuid.UUID,
    upi_id: str,
    authenticated_at: datetime | None,
    now: datetime,
) -> None:
    """Refuse to replace the ID in effect from a login under a week old (D-109).

    A first ID, or the one already in effect, is never held back: only
    moving where brands pay to somewhere new is what a SIM swapper wants.
    Raises LoginTooRecent.
    """
    current = in_effect(*_rows(db, creator_id), now)
    if current is not None and current.upi_id != upi_id:
        account_id = db.scalars(
            select(Creator.account_id).where(Creator.id == creator_id)
        ).one()
        login_age.ensure_established_unless_passkey(db, account_id, authenticated_at, now)


def ensure_may_replace_for_account(
    db: Session,
    account: Account,
    upi_id: str,
    authenticated_at: datetime | None,
    now: datetime,
) -> None:
    """`ensure_may_replace` for an account, before a code is sent for `upi_id`.

    An account without a creator profile has no ID to replace.
    """
    creator_id = db.scalars(
        select(Creator.id).where(Creator.account_id == account.id)
    ).first()
    if creator_id is not None:
        ensure_may_replace(db, creator_id, upi_id, authenticated_at, now)


def cancel_waiting(
    db: Session, account: Account, creator: Creator, now: datetime
) -> None:
    """Drop a new UPI ID still waiting, so it never reaches a brand.

    No code is asked for: cancelling only keeps the ID brands already see,
    and the owner must be able to do it even when someone else holds their
    number. Nothing waiting is fine, and safe to repeat. Raises
    UpiChangeAlreadyInEffect when the wait is already over.
    """
    db.execute(select(Creator.id).where(Creator.id == creator.id).with_for_update())
    _, change = _rows(db, creator.id)
    if change is None:
        # Nothing written: this only ends the transaction and its lock.
        db.commit()
        return
    if now >= change.usable_at:
        db.rollback()
        raise UpiChangeAlreadyInEffect()
    db.delete(change)
    notifications.record(
        db, account_id=account.id, notification_type="upi_change_cancelled", now=now
    )
    db.commit()


def _fold(
    db: Session,
    creator_id: uuid.UUID,
    current: CreatorUpi | None,
    change: CreatorUpiChange | None,
    now: datetime,
) -> tuple[CreatorUpi | None, CreatorUpiChange | None]:
    """Write a change whose wait is over into `creator_upi`. The caller commits.

    Only tidying: `in_effect` already answers with it. `updated_at` is when
    its wait ended, which is when brands began to see it.
    """
    if change is None or now < change.usable_at:
        return current, change
    if current is None:
        current = CreatorUpi(creator_id=creator_id, created_at=change.created_at)
        db.add(current)
    current.upi_id = change.upi_id
    current.consented_at = change.consented_at
    current.notice_version = change.notice_version
    current.updated_at = change.usable_at
    db.delete(change)
    db.flush()
    return current, None


def remove_for_creator(db: Session, creator: Creator) -> None:
    """Withdraw: the UPI ID, any new one waiting, and their consent, deleted at once.

    Always allowed, even while adding one is not open, and with no code:
    withdrawing consent must be as easy as giving it (DPDP Act section 6),
    and removing an ID sends no money anywhere new.
    """
    db.execute(delete(CreatorUpi).where(CreatorUpi.creator_id == creator.id))
    db.execute(delete(CreatorUpiChange).where(CreatorUpiChange.creator_id == creator.id))
    db.commit()


def pay_link(upi_id: str, payee_name: str, amount_paise: int, note: str) -> str:
    """NPCI's `upi://pay` link for paying one person.

    Only the person-to-person fields: payee address, payee name, amount,
    currency and note. The merchant fields (`tr`, `mc`) are for registered
    merchants, which a creator is not. Every value is percent-encoded, with a
    space as %20, as the linking specification asks.
    """
    rupees, paise = divmod(amount_paise, 100)
    fields = {
        "pa": upi_id,
        "pn": payee_name,
        "am": f"{rupees}.{paise:02d}",
        "cu": "INR",
        "tn": note[:NOTE_MAX_LENGTH],
    }
    return "upi://pay?" + "&".join(
        f"{key}={quote(value, safe='')}" for key, value in fields.items()
    )


def pay_details(
    db: Session, memo: DealMemo, payment: PaymentStatus, now: datetime
) -> PayDetails:
    """What the brand on this deal needs to pay its creator by UPI.

    Only while the payment is open: once the brand has marked it sent, the
    creator's UPI ID has done its job and is not shown again. Raises
    PaymentAlreadyMarkedPaid.
    """
    if payment.marked_paid_at is not None:
        raise PaymentAlreadyMarkedPaid(
            "This payment is already marked as sent, so its pay details are closed."
        )
    creator, title = db.execute(
        select(Creator, Campaign.title)
        .join(Application, Application.creator_id == Creator.id)
        .join(Campaign, Campaign.id == Application.campaign_id)
        .where(Application.id == memo.application_id)
    ).one()
    upi = get_for_creator(db, creator, now).in_effect

    reason: str | None = None
    if upi is None:
        reason = "no_upi_id"
    elif payment.amount_paise > UPI_PERSON_TO_PERSON_LIMIT_PAISE:
        reason = "above_upi_limit"

    return PayDetails(
        payee_name=creator.display_name,
        upi_id=upi.upi_id if upi is not None else None,
        amount_paise=payment.amount_paise,
        pay_link=(
            pay_link(upi.upi_id, creator.display_name, payment.amount_paise, title)
            if upi is not None and reason is None
            else None
        ),
        unavailable_reason=reason,
        upi_id_set_at=upi.set_at if upi is not None else None,
        upi_id_changed_recently=upi is not None and now - upi.set_at < RECENT_CHANGE,
    )


def export_for_account(db: Session, account_id: uuid.UUID) -> list[ExportedSection]:
    """The creator's own UPI ID, any new one waiting, and the consent of each.

    Nothing for a brand: brands give no UPI ID.
    """
    creator = db.scalars(select(Creator).where(Creator.account_id == account_id)).first()
    if creator is None:
        return []
    current, change = _rows(db, creator.id)
    return [
        build_section(
            "upi_id",
            table="creator_upi",
            purpose=(
                "The UPI ID you gave so brands on your deals can pay you "
                "directly, when you gave it, and the version of the notice you "
                "agreed to. Brands see it only while a payment to you is open."
            ),
            objects=[current] if current is not None else [],
            fields=EXPORT_FIELDS,
        ),
        build_section(
            "upi_id_change",
            table="creator_upi_change",
            purpose=(
                "A new UPI ID you asked for, with the consent you gave for it, "
                "and when brands start to see it: a new ID waits 24 hours, so "
                "someone who took over your number cannot be paid in your "
                "place before you notice. Once that time has passed, it is "
                "the ID brands see."
            ),
            objects=[change] if change is not None else [],
            fields=CHANGE_EXPORT_FIELDS,
        ),
    ]
