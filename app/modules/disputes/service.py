"""Dispute rules (D-028). We record; we do not judge.

Nothing in this file decides who is right, and that is the design rather than
a gap in it. We hold no money and have no standing, so a finding from us
would be a promise we cannot keep and a liability we cannot carry. What we
can do is keep an honest, dated account that either side can take away and
use wherever it actually counts.

`unresolved` is derived, not stored: nobody does it, it is what thirty days
of nothing looks like. Storing it would need a scheduled job, and a row could
then say `open` long after both parties had walked away.
"""

import uuid
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import india_date
from app.core.export import (
    MAX_ROWS_PER_SECTION,
    ExportedSection,
    allow,
    build_section,
)
from app.modules.disputes.event_models import DisputeEvent
from app.modules.disputes.exceptions import (
    DisputeAlreadyClosed,
    DisputeAlreadyOpen,
    DisputeNotFound,
    NotADisputeParty,
    UnknownDisputeOutcome,
)
from app.modules.disputes.models import (
    DISPUTE_OUTCOMES,
    DISPUTE_PARTIES,
    RESPONSE_WINDOW_DAYS,
    UNRESOLVED_AFTER_DAYS,
    Dispute,
)

# Tables this module answers for in a data export. D-028 promises that
# either party can export the timeline, so this is part of the decision
# rather than an addition to it.
EXPORTED_TABLES = frozenset({"dispute", "dispute_event"})

DISPUTE_EXPORT_FIELDS = allow(
    "id",
    "payment_status_id",
    "opened_by",
    "reason",
    "response_due_on",
    "outcome",
    "closed_at",
    "created_at",
    "updated_at",
)

EVENT_EXPORT_FIELDS = allow(
    "id",
    "dispute_id",
    "actor_role",
    "kind",
    "note",
    "evidence_url",
    "created_at",
    "updated_at",
)

OPEN = "open"
UNRESOLVED = "unresolved"

DISPUTE_STATES: tuple[str, ...] = (OPEN, UNRESOLVED, *DISPUTE_OUTCOMES)


def response_deadline_for(opened_on: date) -> date:
    """When the other side's window to put their account on the record ends."""
    return opened_on + timedelta(days=RESPONSE_WINDOW_DAYS)


def unresolved_on(dispute: Dispute) -> date:
    """The day silence stops being a wait and is recorded as silence."""
    return india_date(dispute.created_at) + timedelta(days=UNRESOLVED_AFTER_DAYS)


def derive_state(dispute: Dispute, today: date) -> str:
    """What this dispute is, as of today.

    `unresolved` is a fact about the dispute, never a verdict about either
    person. It says thirty days passed and nothing was agreed, which is all
    anybody here knows.
    """
    if dispute.outcome is not None:
        return dispute.outcome
    if today >= unresolved_on(dispute):
        return UNRESOLVED
    return OPEN


def is_open(dispute: Dispute, today: date) -> bool:
    """Still live: raised, not settled, not yet timed out.

    This is what holds a payment at `late` instead of letting it harden into
    `unpaid` (D-027): a payment somebody is actively arguing about is not
    the same as a payment nobody will discuss.
    """
    return derive_state(dispute, today) == OPEN


def check_party(role: str) -> str:
    if role not in DISPUTE_PARTIES:
        raise NotADisputeParty()
    return role


def check_outcome(outcome: str) -> str:
    if outcome not in DISPUTE_OUTCOMES:
        raise UnknownDisputeOutcome(
            f"Use one of: {', '.join(DISPUTE_OUTCOMES)}."
        )
    return outcome


def get_for_payment(db: Session, payment_id: uuid.UUID) -> Dispute | None:
    return db.scalars(
        select(Dispute).where(Dispute.payment_status_id == payment_id)
    ).first()


def open_payment_ids(
    db: Session, payment_ids: set[uuid.UUID], today: date
) -> set[uuid.UUID]:
    """Which of these payments have a live dispute, in one query.

    Used by the payment record and the brand's reliability record, so that
    neither hardens a disputed payment into non-payment.
    """
    if not payment_ids:
        return set()
    disputes = db.scalars(
        select(Dispute).where(
            Dispute.payment_status_id.in_(payment_ids), Dispute.outcome.is_(None)
        )
    ).all()
    return {
        dispute.payment_status_id for dispute in disputes if is_open(dispute, today)
    }


def _add_event(
    db: Session,
    dispute: Dispute,
    *,
    actor_role: str,
    kind: str,
    now: datetime,
    note: str | None = None,
    evidence_url: str | None = None,
) -> DisputeEvent:
    event = DisputeEvent(
        dispute_id=dispute.id,
        actor_role=actor_role,
        kind=kind,
        note=note,
        evidence_url=evidence_url,
        created_at=now,
        updated_at=now,
    )
    db.add(event)
    return event


def open_for_payment(
    db: Session,
    payment_id: uuid.UUID,
    *,
    opened_by: str,
    reason: str,
    now: datetime,
) -> Dispute:
    """Raise a dispute about a payment. Either side may.

    The reason is written onto the timeline as its first entry, so the
    record reads as one story from the beginning rather than starting
    halfway through.
    """
    check_party(opened_by)
    if get_for_payment(db, payment_id) is not None:
        raise DisputeAlreadyOpen()

    opened_on = india_date(now)
    dispute = Dispute(
        payment_status_id=payment_id,
        opened_by=opened_by,
        reason=reason,
        response_due_on=response_deadline_for(opened_on),
        created_at=now,
        updated_at=now,
    )
    db.add(dispute)
    db.flush()
    _add_event(db, dispute, actor_role=opened_by, kind="opened", note=reason, now=now)
    return dispute


def add_entry(
    db: Session,
    dispute: Dispute,
    *,
    actor_role: str,
    now: datetime,
    note: str | None = None,
    evidence_url: str | None = None,
    kind: str = "evidence",
) -> DisputeEvent:
    """Put something on the record.

    Allowed after the response window has passed, and after the dispute has
    timed out: a late account is still an account, and refusing it would
    make the record less true rather than more orderly. It is not allowed
    once an outcome has been agreed, because that record is finished.
    """
    check_party(actor_role)
    if dispute.outcome is not None:
        raise DisputeAlreadyClosed()

    event = _add_event(
        db,
        dispute,
        actor_role=actor_role,
        kind=kind,
        note=note,
        evidence_url=evidence_url,
        now=now,
    )
    dispute.updated_at = now
    db.commit()
    db.refresh(event)
    return event


def close(
    db: Session,
    dispute: Dispute,
    *,
    outcome: str,
    actor_role: str,
    now: datetime,
    note: str | None = None,
) -> Dispute:
    """Record how it ended.

    Either side may close it, including long after it timed out, because
    most of these end with a phone call and the record should be allowed to
    catch up with what really happened (D-028).
    """
    check_party(actor_role)
    check_outcome(outcome)
    if dispute.outcome is not None:
        raise DisputeAlreadyClosed()

    dispute.outcome = outcome
    dispute.closed_at = now
    dispute.updated_at = now
    _add_event(
        db,
        dispute,
        actor_role=actor_role,
        kind="closed",
        note=note or outcome.replace("_", " "),
        now=now,
    )
    db.commit()
    db.refresh(dispute)
    return dispute


def timeline(db: Session, dispute: Dispute) -> list[DisputeEvent]:
    """Every entry, oldest first. The order is the point."""
    return list(
        db.scalars(
            select(DisputeEvent)
            .where(DisputeEvent.dispute_id == dispute.id)
            .order_by(DisputeEvent.created_at, DisputeEvent.id)
        ).all()
    )


def get_or_404(db: Session, payment_id: uuid.UUID) -> Dispute:
    dispute = get_for_payment(db, payment_id)
    if dispute is None:
        raise DisputeNotFound()
    return dispute


def export_for_account(db: Session, account_id: uuid.UUID) -> list[ExportedSection]:
    """Disputes on this account's deals, and every entry on their timelines.

    D-028 promises either party can export the timeline. This is that
    promise: both sides get the same dated account, including the words the
    other one wrote, because a one-sided record would be no use to anybody
    trying to show what happened.
    """
    from app.modules.deal_memo import service as deal_memos
    from app.modules.payment_status.models import PaymentStatus

    memos = deal_memos.memos_for_account(db, account_id, limit=MAX_ROWS_PER_SECTION + 1)
    memo_ids = {memo.id for memo in memos}

    disputes: list[Dispute] = []
    events: list[DisputeEvent] = []
    if memo_ids:
        payment_ids = set(
            db.scalars(
                select(PaymentStatus.id).where(
                    PaymentStatus.deal_memo_id.in_(memo_ids)
                )
            ).all()
        )
        if payment_ids:
            disputes = list(
                db.scalars(
                    select(Dispute)
                    .where(Dispute.payment_status_id.in_(payment_ids))
                    .order_by(Dispute.created_at, Dispute.id)
                    .limit(MAX_ROWS_PER_SECTION + 1)
                ).all()
            )
        if disputes:
            events = list(
                db.scalars(
                    select(DisputeEvent)
                    .where(DisputeEvent.dispute_id.in_({d.id for d in disputes}))
                    .order_by(DisputeEvent.created_at, DisputeEvent.id)
                    .limit(MAX_ROWS_PER_SECTION + 1)
                ).all()
            )

    return [
        build_section(
            "disputes",
            table="dispute",
            purpose=(
                "Disagreements raised about a payment on one of your deals, "
                "and how each ended. We record these; we never decide who was "
                "right."
            ),
            objects=disputes,
            fields=DISPUTE_EXPORT_FIELDS,
        ),
        build_section(
            "dispute_timeline",
            table="dispute_event",
            purpose=(
                "What each side put on the record and when, in order. Yours "
                "to take anywhere you need it."
            ),
            objects=events,
            fields=EVENT_EXPORT_FIELDS,
        ),
    ]
