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
  the answer says when the ID was last set and flags a change in the last
  24 hours; the brand's UPI app shows the bank's name for the payee before
  the PIN, which is the check that matters, and the brand is told to read it.
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
from app.modules.auth.models.creator import Creator
from app.modules.campaigns.models import Application, Campaign
from app.modules.deal_memo.models import DealMemo
from app.modules.payment_status.exceptions import (
    PaymentAlreadyMarkedPaid,
    UpiNoticeChanged,
    UpiNotOpenYet,
)
from app.modules.payment_status.models import PaymentStatus
from app.modules.payment_status.upi_models import CreatorUpi

EXPORTED_TABLES = frozenset({"creator_upi"})
EXPORT_FIELDS = allow(
    "upi_id", "consented_at", "notice_version", "created_at", "updated_at"
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
class PayDetails:
    payee_name: str
    upi_id: str | None
    amount_paise: int
    pay_link: str | None
    unavailable_reason: str | None
    upi_id_set_at: datetime | None
    upi_id_changed_recently: bool


def get_for_creator(db: Session, creator: Creator) -> CreatorUpi | None:
    return db.scalars(
        select(CreatorUpi).where(CreatorUpi.creator_id == creator.id)
    ).first()


def set_for_creator(
    db: Session, creator: Creator, upi_id: str, notice_version: str, now: datetime
) -> CreatorUpi:
    """Store the creator's UPI ID with their consent, replacing any earlier one.

    Consent is given again with every change, against the notice in force:
    a creator who read an older notice is sent back to read the new one.
    One INSERT ... ON CONFLICT, so two saves at once cannot collide.
    Raises UpiNotOpenYet and UpiNoticeChanged.
    """
    if settings.upi_notice_version is None:
        raise UpiNotOpenYet(
            "Its notice is not ready yet. Until then, brands pay you by bank "
            "transfer or by the UPI ID you give them."
        )
    if notice_version != settings.upi_notice_version:
        raise UpiNoticeChanged()
    values = {
        "upi_id": upi_id,
        "consented_at": now,
        "notice_version": notice_version,
        "updated_at": now,
    }
    db.execute(
        insert(CreatorUpi)
        .values(creator_id=creator.id, created_at=now, **values)
        .on_conflict_do_update(index_elements=[CreatorUpi.creator_id], set_=values)
    )
    db.commit()
    row = db.scalars(
        select(CreatorUpi)
        .where(CreatorUpi.creator_id == creator.id)
        .execution_options(populate_existing=True)
    ).one()
    return row


def remove_for_creator(db: Session, creator: Creator) -> None:
    """Withdraw: the UPI ID and its consent are deleted at once.

    Always allowed, even while adding one is not open: withdrawing consent
    must be as easy as giving it (DPDP Act section 6).
    """
    db.execute(delete(CreatorUpi).where(CreatorUpi.creator_id == creator.id))
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
    upi = get_for_creator(db, creator)

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
        upi_id_set_at=upi.updated_at if upi is not None else None,
        upi_id_changed_recently=upi is not None and now - upi.updated_at < RECENT_CHANGE,
    )


def export_for_account(db: Session, account_id: uuid.UUID) -> list[ExportedSection]:
    """The creator's own UPI ID and the consent it was given under.

    Nothing for a brand: brands give no UPI ID.
    """
    creator = db.scalars(select(Creator).where(Creator.account_id == account_id)).first()
    if creator is None:
        return []
    upi = get_for_creator(db, creator)
    rows = [upi] if upi is not None else []
    return [
        build_section(
            "upi_id",
            table="creator_upi",
            purpose=(
                "The UPI ID you gave so brands on your deals can pay you "
                "directly, when you gave it, and the version of the notice you "
                "agreed to. Brands see it only while a payment to you is open."
            ),
            objects=rows,
            fields=EXPORT_FIELDS,
        )
    ]
