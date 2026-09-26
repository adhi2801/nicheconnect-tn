"""Payment record rules (D-027). We record payment; we never hold it.

The important function here is `derive_state`. The table stores facts, and
this reads a state out of them against today's date, so no scheduled job is
needed and no row can ever claim a payment is on time when it is a month
overdue. See `models.py` for why that choice was made.
"""

import re
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.clock import india_date
from app.core.errors import DomainError
from app.core.export import (
    MAX_ROWS_PER_SECTION,
    ExportedSection,
    allow,
    build_section,
)
from app.core.taxonomy import CURRENCY
from app.modules.campaigns.models import Application, Campaign
from app.modules.deal_memo import record_service as record
from app.modules.deal_memo import service as deal_memos
from app.modules.deal_memo.exceptions import MemoNotFound
from app.modules.deal_memo.models import DealMemo
from app.modules.payment_status.exceptions import (
    BarterMemoHasNoPayment,
    InvalidPaymentReference,
    PaymentAlreadyConfirmed,
    PaymentAlreadyMarkedPaid,
    PaymentNotMarkedPaid,
    PaymentRecordExists,
    PaymentRecordNotFound,
    UnknownPaymentMethod,
)
from app.modules.payment_status.models import (
    PAYMENT_METHODS,
    REFERENCE_MAX_LENGTH,
    PaymentStatus,
)

# Tables this module answers for in a data export. A payment record is about
# money owed to a person, so both parties are entitled to a copy of it.
EXPORTED_TABLES = frozenset({"payment_status"})

EXPORT_FIELDS = allow(
    "id",
    "deal_memo_id",
    "amount_paise",
    "currency",
    "due_on",
    "method",
    "reference",
    "marked_paid_at",
    "confirmed_at",
    "created_at",
    "updated_at",
)

# States, read from the facts. Never stored.
DUE = "due"
LATE = "late"
UNPAID = "unpaid"
PAID = "paid"
UNCONFIRMED = "unconfirmed"
CONFIRMED = "confirmed"

PAYMENT_STATES: tuple[str, ...] = (DUE, LATE, UNPAID, PAID, UNCONFIRMED, CONFIRMED)

# How long a creator has to confirm before the record says so plainly.
#
# Most people who have been paid never come back to tick a box; not
# confirming is the common case, not an edge case. Leaving the record at
# `paid` forever would let a brand that genuinely paid look permanently
# unconfirmed through nobody's fault.
#
# We do NOT auto-confirm. Confirmation is the creator's statement about their
# own income, and putting words in their mouth would be the one thing in this
# product that asserts something we do not know. `unconfirmed` says exactly
# what happened: the brand says it paid, the creator never answered. It is
# not an accusation of either of them (D-028: we record, we do not judge).
#
# A late confirmation is still accepted and still moves the record to
# `confirmed`; this window only changes what the record says in the meantime.
CONFIRMATION_WINDOW_DAYS = 7

# How long after the due date silence becomes the stronger `unpaid` state.
#
# D-027 says "21 days", and its reasoning gives "silence at day 25" as the
# example — which only works if those 21 days run from approval, not from the
# due date. With the default 7-day payment window that is 14 days after the
# due date, which is what this is.
#
# It is expressed relative to the due date on purpose. Counting from approval
# would make a memo with a 30-day payment window turn `unpaid` nine days
# before the money was even due, which is nonsense the database would happily
# store. Worth confirming with a founder; changing it is one number.
UNPAID_AFTER_DUE_DAYS = 14

# A UPI or IMPS reference is a 12-digit RRN. It is the only one with a fixed,
# machine-checkable shape, which is why D-027 allows automatic matching for
# UPI alone: a NEFT UTR is 16 alphanumeric characters and an RTGS UTR is 22,
# neither of which a statement feed can be matched on as reliably.
UPI_RRN = re.compile(r"^\d{12}$")

# Deliberately loose. A reference is evidence, and refusing to record a real
# payment because the brand's app showed an unusual transaction id would be a
# worse failure than storing a reference we cannot match automatically. So
# anything printable and sensibly sized is accepted, and matchability is a
# separate question that `is_auto_matchable` answers.
REFERENCE_MIN_LENGTH = 4
PRINTABLE_REFERENCE = re.compile(r"^[\w\-/.:# ]+$")


def due_date_for(approved_on: date, payment_due_days: int) -> date:
    """When payment is due: the approval date plus the memo's own window."""
    return approved_on + timedelta(days=payment_due_days)


def unpaid_date_for(due_on: date) -> date:
    """The day silence stops being lateness and becomes non-payment."""
    return due_on + timedelta(days=UNPAID_AFTER_DUE_DAYS)


def confirmation_deadline(payment: PaymentStatus) -> date:
    """The day after which silence from the creator is stated as silence."""
    if payment.marked_paid_at is None:
        raise ValueError("Only a payment marked as paid has a confirmation deadline")
    return india_date(payment.marked_paid_at) + timedelta(days=CONFIRMATION_WINDOW_DAYS)


def derive_state(
    payment: PaymentStatus, today: date, *, has_open_dispute: bool = False
) -> str:
    """What this payment record means, as of `today`.

    `has_open_dispute` is always False until the dispute table exists
    (D-028). The argument is here because D-027 makes `unpaid` conditional on
    there being no dispute, and leaving the seam is more honest than
    pretending the condition does not exist.
    """
    if payment.confirmed_at is not None:
        return CONFIRMED
    if payment.marked_paid_at is not None:
        if today >= confirmation_deadline(payment):
            return UNCONFIRMED
        return PAID
    if today <= payment.due_on:
        return DUE
    if not has_open_dispute and today >= unpaid_date_for(payment.due_on):
        return UNPAID
    return LATE


def days_overdue(payment: PaymentStatus, today: date) -> int:
    """How many days past due, or 0 if it is not overdue."""
    if payment.marked_paid_at is not None or today <= payment.due_on:
        return 0
    return (today - payment.due_on).days


def is_auto_matchable(payment: PaymentStatus) -> bool:
    """Whether this reference could be matched against a statement feed.

    Only UPI, and only when the reference really is a 12-digit RRN (D-027).
    """
    if payment.method != "upi" or payment.reference is None:
        return False
    return bool(UPI_RRN.fullmatch(payment.reference))


def check_method(method: str) -> str:
    if method not in PAYMENT_METHODS:
        raise UnknownPaymentMethod(f"Use one of: {', '.join(PAYMENT_METHODS)}.")
    return method


def clean_reference(reference: str) -> str:
    """Tidy and sanity-check a payment reference.

    Kept permissive on purpose: see REFERENCE_MIN_LENGTH above.
    """
    tidied = " ".join(reference.split())
    if not REFERENCE_MIN_LENGTH <= len(tidied) <= REFERENCE_MAX_LENGTH:
        raise InvalidPaymentReference(
            f"Give {REFERENCE_MIN_LENGTH} to {REFERENCE_MAX_LENGTH} characters: "
            "the UPI reference number, the bank UTR, or a note saying how cash "
            "was handed over."
        )
    if not PRINTABLE_REFERENCE.fullmatch(tidied):
        raise InvalidPaymentReference("Use letters, digits, spaces or - / . : # only.")
    return tidied


def create_for_memo(
    db: Session,
    memo: DealMemo,
    *,
    approved_on: date,
    now: datetime,
) -> PaymentStatus:
    """Open the payment record for an accepted memo whose work was approved.

    The amount and the due date are copied in rather than read through the
    memo, so the record stays true to what was agreed even if terms or
    policy change later.
    """
    # Barter memos carry no fee (D-024), so there is no payment to record.
    # Without this the row would fail the NOT NULL on amount_paise, which is
    # a database error where the caller deserves a reason.
    if memo.fee_amount_paise is None:
        raise BarterMemoHasNoPayment()

    existing = db.scalars(
        select(PaymentStatus).where(PaymentStatus.deal_memo_id == memo.id)
    ).first()
    if existing is not None:
        raise PaymentRecordExists()

    payment = PaymentStatus(
        deal_memo_id=memo.id,
        amount_paise=memo.fee_amount_paise,
        currency=CURRENCY,
        due_on=due_date_for(approved_on, memo.payment_due_days),
        created_at=now,
        updated_at=now,
    )
    db.add(payment)
    try:
        # The check above can be passed by two callers at once; the unique
        # index on deal_memo_id is what actually holds the line, so its
        # error becomes the same answer the check would have given.
        db.flush()
    except IntegrityError as error:
        db.rollback()
        raise PaymentRecordExists() from error
    # Opened by the deal's own rule (approval starts the clock, D-027), not
    # by either person, so the record names us as the actor.
    record.append(
        db,
        memo,
        kind="payment_opened",
        actor_role="system",
        now=now,
        facts={
            "payment_id": str(payment.id),
            "amount_paise": payment.amount_paise,
            "due_on": payment.due_on.isoformat(),
        },
    )
    return payment


def mark_paid(
    db: Session,
    payment: PaymentStatus,
    *,
    method: str,
    reference: str,
    now: datetime,
) -> PaymentStatus:
    """The brand says it sent the money. Only the brand may do this.

    The row is locked before it is read, because reading and then writing
    without one lets two simultaneous taps both pass the check and both
    write: proven with four concurrent calls, three of which won. On a
    money record the second write would silently replace the method and
    reference of the first, so the record could say cash when the brand
    sent UPI. The lock makes exactly one win and the rest get a clean 409.
    """
    _record_marked_paid(db, payment, method=method, reference=reference, now=now)
    db.commit()
    db.refresh(payment)
    return payment


def _record_marked_paid(
    db: Session, payment: PaymentStatus, *, method: str, reference: str, now: datetime
) -> None:
    """The change `mark_paid` makes, without committing it.

    Shared with the bulk path, so a payment marked in a batch is marked by
    exactly the same rules, lock and notification as one marked alone.
    """
    db.refresh(payment, with_for_update=True)
    if payment.marked_paid_at is not None:
        raise PaymentAlreadyMarkedPaid()

    payment.method = check_method(method)
    payment.reference = clean_reference(reference)
    payment.marked_paid_at = now
    payment.updated_at = now
    # The reference is typed, so the record keeps its fingerprint.
    record.append_for_payment(
        db,
        payment.id,
        kind="payment_marked_paid",
        actor_role="brand",
        now=now,
        facts={
            "payment_id": str(payment.id),
            "method": payment.method,
            "reference_sha256": record.fingerprint(payment.reference),
        },
    )
    # The creator has no other way to know they should look for the money.
    memo = db.get(DealMemo, payment.deal_memo_id)
    if memo is not None:
        deal_memos.notify_party(
            db, memo, to="creator", notification_type="payment_marked_paid", now=now
        )


def confirm_received(
    db: Session, payment: PaymentStatus, *, now: datetime
) -> PaymentStatus:
    """The creator says the money arrived. Only the creator may do this.

    Locked first, for the same reason as mark_paid.
    """
    db.refresh(payment, with_for_update=True)
    if payment.confirmed_at is not None:
        raise PaymentAlreadyConfirmed()
    if payment.marked_paid_at is None:
        raise PaymentNotMarkedPaid()

    payment.confirmed_at = now
    payment.updated_at = now
    record.append_for_payment(
        db,
        payment.id,
        kind="payment_confirmed",
        actor_role="creator",
        now=now,
        facts={"payment_id": str(payment.id)},
    )
    memo = db.get(DealMemo, payment.deal_memo_id)
    if memo is not None:
        deal_memos.notify_party(
            db, memo, to="brand", notification_type="payment_confirmed", now=now
        )
    db.commit()
    db.refresh(payment)
    return payment


def get_for_memo(db: Session, memo_id: uuid.UUID) -> PaymentStatus | None:
    return db.scalars(
        select(PaymentStatus).where(PaymentStatus.deal_memo_id == memo_id)
    ).first()


def list_outstanding(db: Session, *, on: date, limit: int = 100) -> list[PaymentStatus]:
    """Payments not marked paid and past their due date, oldest first.

    This is the query the partial index exists for, and the one the reminder
    job will use once a job runner is chosen (D-029).
    """
    return list(
        db.scalars(
            select(PaymentStatus)
            .where(
                PaymentStatus.marked_paid_at.is_(None),
                PaymentStatus.due_on < on,
            )
            .order_by(PaymentStatus.due_on, PaymentStatus.id)
            .limit(limit)
        ).all()
    )


def export_for_account(db: Session, account_id: uuid.UUID) -> list[ExportedSection]:
    """Payment records on memos this account is a party to.

    Both sides get the same row: it is the shared record of what was owed
    and what each of them said happened to it.
    """
    memos = deal_memos.memos_for_account(db, account_id, limit=MAX_ROWS_PER_SECTION + 1)
    memo_ids = {memo.id for memo in memos}

    rows: list[PaymentStatus] = []
    if memo_ids:
        rows = list(
            db.scalars(
                select(PaymentStatus)
                .where(PaymentStatus.deal_memo_id.in_(memo_ids))
                .order_by(PaymentStatus.due_on, PaymentStatus.id)
                .limit(MAX_ROWS_PER_SECTION + 1)
            ).all()
        )

    return [
        build_section(
            "payments",
            table="payment_status",
            purpose=(
                "What was owed on each deal, by when, what the brand said it "
                "sent and whether the creator confirmed it arrived. "
                "NicheConnect TN never holds this money; the row is only the "
                "record of it."
            ),
            objects=rows,
            fields=EXPORT_FIELDS,
        )
    ]


def open_on_approval(
    db: Session, memo: DealMemo, *, approved_at: datetime, now: datetime
) -> PaymentStatus | None:
    """Open the payment record because the work was approved (D-027).

    Called from proof approval, which happens both when a brand approves and
    when the window lapses, so this has to be safe to run more than once.
    Returns None when there is nothing to record: a barter memo carries no
    fee, and a record already opened is not opened again.
    """
    if memo.fee_amount_paise is None:
        return None
    existing = get_for_memo(db, memo.id)
    if existing is not None:
        return existing
    return create_for_memo(db, memo, approved_on=india_date(approved_at), now=now)


# --- many at once ---------------------------------------------------------------
#
# A brand that pays several creators in one bank bulk transfer gets one
# reference per row back from the bank, and the bank may reject some rows
# while others go through. So each row here is recorded or refused on its
# own: a typo in row 7 must not hold back the other creators' notice that
# their money is on its way.

# Kept small enough that one request stays inside the 500 ms write budget
# (backend.md section 6); measured, not guessed.
MAX_BULK_MARK_PAID = 25


@dataclass(frozen=True)
class BulkMarkPaidRow:
    memo_id: uuid.UUID
    method: str
    reference: str


@dataclass(frozen=True)
class BulkMarkPaidOutcome:
    """One row's result: the payment it recorded, or the reason it was refused."""

    memo_id: uuid.UUID
    payment: PaymentStatus | None
    refusal: DomainError | None


def mark_paid_in_bulk(
    db: Session, brand_id: uuid.UUID, rows: list[BulkMarkPaidRow], *, now: datetime
) -> list[BulkMarkPaidOutcome]:
    """Record several payments, each on its own, in the order given.

    Every row makes exactly the change a single `mark_paid` makes: the same
    lock, checks and notification. A memo that is not this brand's is
    refused as not found, never as someone else's (security.md section 2).

    Each row runs in its own savepoint, so a refused row undoes only its own
    changes and nothing else in the session. The recorded rows are committed
    together, once, at the end: an unexpected failure part-way leaves none
    of them recorded rather than some.
    """
    # One query for every row: the memo, if it is this brand's, and its
    # payment record, if one has been opened.
    found: dict[uuid.UUID, PaymentStatus | None] = {
        memo_id: payment
        for memo_id, payment in db.execute(
            select(DealMemo.id, PaymentStatus)
            .join(Application, Application.id == DealMemo.application_id)
            .join(Campaign, Campaign.id == Application.campaign_id)
            .outerjoin(PaymentStatus, PaymentStatus.deal_memo_id == DealMemo.id)
            .where(
                Campaign.brand_id == brand_id,
                DealMemo.id.in_([row.memo_id for row in rows]),
            )
        ).tuples()
    }

    outcomes: list[BulkMarkPaidOutcome] = []
    for row in rows:
        savepoint = db.begin_nested()
        try:
            if row.memo_id not in found:
                raise MemoNotFound()
            payment = found[row.memo_id]
            if payment is None:
                raise PaymentRecordNotFound(
                    "A payment record opens when the work is approved; this deal "
                    "has no approved work yet, or it is a barter deal."
                )
            _record_marked_paid(
                db, payment, method=row.method, reference=row.reference, now=now
            )
        except DomainError as refusal:
            savepoint.rollback()
            outcomes.append(BulkMarkPaidOutcome(row.memo_id, None, refusal))
        else:
            savepoint.commit()
            outcomes.append(BulkMarkPaidOutcome(row.memo_id, payment, None))
    db.commit()
    return outcomes
