"""A deal's agreed dates as calendar events (item 69, D-102).

Only an accepted deal has agreed dates; any other gets an empty calendar,
which is a valid file. The events, each with a reminder a day before:

- the content due date in the memo, all day;
- while proof waits for the brand, the moment it approves itself (D-025);
- while the payment is unconfirmed, its due date, all day.

Both parties get the same file. Each event's UID is fixed per deal and kind,
so adding the file again after a change moves the event rather than adding
a second one. The words are facts and the safety line from
trust-and-safety.md section 5, never a promise about money (constraint 1).
A fixed number of queries whatever the deal's history.
"""

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, noload

from app.modules.campaigns.models import Application, Campaign
from app.modules.deal_memo.calendar_ics import Event
from app.modules.deal_memo.models import DealMemo
from app.modules.deal_memo.proof_models import DeliverableProof
from app.modules.deal_memo.proof_service import approval_deadline
from app.modules.payment_status.models import PaymentStatus

REMIND = timedelta(hours=24)
SAFETY = "NicheConnect never asks anyone to pay to get a deal."


def uid(memo: DealMemo, kind: str) -> str:
    return f"deal-{memo.id}-{kind}@nicheconnect-tn"


def deal_dates(db: Session, memo: DealMemo) -> tuple[str, list[Event]]:
    """The calendar's name and its events, for either party."""
    title = db.scalar(
        select(Campaign.title)
        .join(Application, Application.campaign_id == Campaign.id)
        .where(Application.id == memo.application_id)
    )
    name = f"Deal: {title}"
    if memo.status != "accepted":
        return name, []

    events: list[Event] = []
    if memo.content_due_on is not None:
        events.append(
            Event(
                uid=uid(memo, "content-due"),
                summary=f"Content due: {title}",
                description=f"The date agreed in the deal memo. {SAFETY}",
                start=memo.content_due_on,
                remind_before=REMIND,
            )
        )

    proofs = list(
        db.scalars(
            select(DeliverableProof)
            # Only the dates are needed: not the screenshots each proof
            # would otherwise load with it.
            .options(noload(DeliverableProof.files))
            .where(DeliverableProof.deal_memo_id == memo.id)
            .order_by(DeliverableProof.created_at, DeliverableProof.id)
        ).all()
    )
    waiting = proofs[-1] if proofs and proofs[-1].status == "submitted" else None
    if waiting is not None:
        events.append(
            Event(
                uid=uid(memo, "proof-approval"),
                summary=f"Proof approves itself: {title}",
                description=(
                    "Unless the brand approves it or asks for changes first, the "
                    f"submitted work is approved at this moment. {SAFETY}"
                ),
                start=approval_deadline(memo, waiting, proofs),
                remind_before=REMIND,
            )
        )

    payment = db.scalar(
        select(PaymentStatus).where(PaymentStatus.deal_memo_id == memo.id)
    )
    if (
        payment is not None
        and payment.confirmed_at is None
        and payment.due_on is not None
    ):
        events.append(
            Event(
                uid=uid(memo, "payment-due"),
                summary=f"Payment due: {title}",
                description=(
                    "The brand pays the creator directly, by UPI or bank transfer. "
                    "The creator checks their own bank app, not a screenshot, then "
                    f"confirms it. {SAFETY}"
                ),
                start=payment.due_on,
                remind_before=REMIND,
            )
        )
    return name, events
