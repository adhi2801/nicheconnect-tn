"""A campaign report a brand can hand to its boss (item 47, D-088).

Every deal on one campaign: who made it, what was agreed, whether the work
was delivered on time and approved, what the screenshots said it reached,
whether the money was sent and confirmed, and the deal record's seal that
proves each line was not edited afterwards. The brand's own campaign only.

Worked out, never stored (`backend.md` section 2): every figure follows from
the memo, its proof, its payment, the readings and the deal record, as of
`now`, with the same rules the rest of the backend uses (`stage_of`,
`is_approved`, `derive_state`). A stored report would be a second truth.

What it never holds about a creator: anything beyond the name and handle
the brand already sees on its payments list. No phone, no UPI ID, and no
payment reference: the record shows typed text only as a fingerprint, and
so does this.

Results are **read from screenshots, never verified** (D-070), and say so.
A reading the creator marked as wrong is counted apart, never summed in.
A figure shown abbreviated on screen (12.5K) is summed as read, and the
report says it includes one.

A memo still in draft is not a deal yet, so it is left out. A campaign's
deals cost the same fixed number of queries whatever their number.
"""

import bisect
import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy import exists, func, select
from sqlalchemy.orm import Session

from app.core.clock import india_date
from app.modules.auth.models.creator import Creator
from app.modules.campaigns.models import APPLICATION_STATUSES, Application, Campaign
from app.modules.campaigns.summary import AGREED_STAGES
from app.modules.deal_memo import proof_reading_service, record_service
from app.modules.deal_memo.anchor_models import DealRecordCheckpoint, DealRecordTimestamp
from app.modules.deal_memo.delivery_record import is_approved
from app.modules.deal_memo.models import DealMemo
from app.modules.deal_memo.proof_models import DeliverableProof, ProofFile
from app.modules.deal_memo.proof_reading_models import READING_METRICS, ProofFileReading
from app.modules.deal_memo.proof_service import approval_deadline
from app.modules.deal_memo.record_models import DealRecordEntry
from app.modules.deal_memo.stage import FINISHED, DealStage, stage_of
from app.modules.disputes import service as disputes
from app.modules.payment_status import service as payments
from app.modules.payment_status.models import PaymentStatus


@dataclass(frozen=True)
class Results:
    """What the approved proof's screenshots said, summed over its files."""

    readings: int
    readings_marked_wrong: int
    includes_abbreviated: bool
    # Each metric's sum over the counted readings; None when none showed it.
    numbers: dict[str, int | None]


@dataclass(frozen=True)
class Seal:
    """The deal record's state: whether it checks, and its latest seal."""

    intact: bool
    entries: int
    latest_seal: str | None
    # The Tamil Nadu date of the first outside-stamped checkpoint that holds
    # the latest seal; None until the next daily checkpoint is stamped.
    stamped_on: date | None


@dataclass(frozen=True)
class DealLine:
    memo: DealMemo
    creator_display_name: str
    creator_handle: str
    stage: DealStage
    first_submitted_on: date | None
    # None while nothing was submitted, or when no date was agreed.
    delivered_on_time: bool | None
    approved_on: date | None
    approved_by_clock: bool
    content_url: str | None
    disclosure_confirmed: bool | None
    payment: PaymentStatus | None
    payment_state: str | None
    # None until the brand says it sent the money.
    paid_on_time: bool | None
    results: Results
    seal: Seal


@dataclass(frozen=True)
class Totals:
    applications: dict[str, int]
    deals: int
    deals_agreed: int
    deals_finished: int
    barter_deals_agreed: int
    agreed_value_paise: int
    marked_paid_paise: int
    confirmed_paise: int
    # Deals with an agreed date whose work was sent: only these can be judged.
    deliveries_judged: int
    delivered_on_time: int
    payments_sent: int
    payments_sent_on_time: int
    results: Results
    records_intact: bool


@dataclass(frozen=True)
class CampaignReport:
    campaign: Campaign
    generated_at: datetime
    deals: list[DealLine]
    totals: Totals


def build_report(db: Session, campaign: Campaign, now: datetime) -> CampaignReport:
    """The whole report for one campaign, in a fixed number of queries.

    The caller has already checked the campaign is the signed-in brand's.
    Raises nothing of its own.
    """
    rows = db.execute(
        select(DealMemo, Creator.display_name, Creator.handle)
        .join(Application, Application.id == DealMemo.application_id)
        .join(Creator, Creator.id == Application.creator_id)
        .where(Application.campaign_id == campaign.id, DealMemo.status != "draft")
        .order_by(DealMemo.created_at, DealMemo.id)
    ).all()
    memos = [memo for memo, _, _ in rows]
    ids = [memo.id for memo in memos]

    proofs = _proofs_by_memo(db, ids)
    payment_by_memo = _payments_by_memo(db, ids)
    today = india_date(now)
    disputed = disputes.open_payment_ids(
        db, {payment.id for payment in payment_by_memo.values()}, today
    )
    approved = {
        memo.id: proof
        for memo in memos
        if (proof := _approved_proof(memo, proofs[memo.id], now)) is not None
    }
    readings = _readings_by_proof(db, [proof.id for proof in approved.values()])
    seals = _seals(db, memos)

    lines = []
    for memo, display_name, handle in rows:
        payment = payment_by_memo.get(memo.id)
        stage = stage_of(
            memo,
            proofs[memo.id],
            payment,
            now,
            has_open_dispute=payment is not None and payment.id in disputed,
        )
        lines.append(
            _line(
                memo,
                display_name,
                handle,
                stage,
                proofs[memo.id],
                approved.get(memo.id),
                payment,
                today,
                readings,
                seals[memo.id],
            )
        )
    return CampaignReport(
        campaign=campaign,
        generated_at=now,
        deals=lines,
        totals=_totals(lines, _application_counts(db, campaign.id)),
    )


# --- loading, one query per kind ---------------------------------------------------------


def _proofs_by_memo(
    db: Session, ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[DeliverableProof]]:
    found: dict[uuid.UUID, list[DeliverableProof]] = defaultdict(list)
    if ids:
        for proof in db.scalars(
            select(DeliverableProof).where(DeliverableProof.deal_memo_id.in_(ids))
        ):
            found[proof.deal_memo_id].append(proof)
    return found


def _payments_by_memo(
    db: Session, ids: list[uuid.UUID]
) -> dict[uuid.UUID, PaymentStatus]:
    if not ids:
        return {}
    return {
        payment.deal_memo_id: payment
        for payment in db.scalars(
            select(PaymentStatus).where(PaymentStatus.deal_memo_id.in_(ids))
        )
    }


def _readings_by_proof(
    db: Session, proof_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[ProofFileReading]]:
    """The shown readings of these proofs' files, grouped by proof."""
    found: dict[uuid.UUID, list[ProofFileReading]] = defaultdict(list)
    if not proof_ids:
        return found
    proof_of_file = {
        file_id: proof_id
        for file_id, proof_id in db.execute(
            select(ProofFile.id, ProofFile.proof_id).where(
                ProofFile.proof_id.in_(proof_ids)
            )
        )
    }
    shown = proof_reading_service.shown_readings(db, list(proof_of_file))
    for file_id, reading in shown.items():
        proof_id = proof_of_file[file_id]
        if proof_id is not None:
            found[proof_id].append(reading)
    return found


def _application_counts(db: Session, campaign_id: uuid.UUID) -> dict[str, int]:
    counts = dict.fromkeys(APPLICATION_STATUSES, 0)
    for status, count in db.execute(
        select(Application.status, func.count())
        .where(Application.campaign_id == campaign_id)
        .group_by(Application.status)
    ):
        counts[status] = count
    return counts


def _seals(db: Session, memos: list[DealMemo]) -> dict[uuid.UUID, Seal]:
    """Each deal's record checked, and when its latest seal was stamped.

    Two queries: every entry of every deal, and the cut-offs of the stamped
    checkpoints. A checkpoint holds each deal's latest seal recorded before
    its cut-off, so the first stamped one after the latest entry holds it.
    """
    entries: dict[uuid.UUID, list[DealRecordEntry]] = defaultdict(list)
    if memos:
        for entry in db.scalars(
            select(DealRecordEntry)
            .where(DealRecordEntry.deal_memo_id.in_([memo.id for memo in memos]))
            .order_by(DealRecordEntry.deal_memo_id, DealRecordEntry.sequence)
        ):
            entries[entry.deal_memo_id].append(entry)
    lasts = [found[-1].recorded_at for found in entries.values() if found]
    cutoffs: list[datetime] = []
    if lasts:
        cutoffs = list(
            db.scalars(
                select(DealRecordCheckpoint.covers_until)
                .where(
                    DealRecordCheckpoint.covers_until > min(lasts),
                    exists().where(
                        DealRecordTimestamp.checkpoint_id == DealRecordCheckpoint.id
                    ),
                )
                .order_by(DealRecordCheckpoint.covers_until)
            )
        )
    seals = {}
    for memo in memos:
        found = entries[memo.id]
        stamped_on = None
        if found:
            at = bisect.bisect_right(cutoffs, found[-1].recorded_at)
            stamped_on = india_date(cutoffs[at]) if at < len(cutoffs) else None
        seals[memo.id] = Seal(
            intact=record_service.verify(memo, found).intact,
            entries=len(found),
            latest_seal=found[-1].entry_hash.hex() if found else None,
            stamped_on=stamped_on,
        )
    return seals


# --- one deal ----------------------------------------------------------------------------


def _approved_proof(
    memo: DealMemo, proofs: list[DeliverableProof], now: datetime
) -> DeliverableProof | None:
    """The latest proof approved, by the brand or by the clock (D-025)."""
    return max(
        (proof for proof in proofs if is_approved(memo, proof, proofs, now)),
        key=lambda proof: (proof.created_at, proof.id),
        default=None,
    )


def _line(
    memo: DealMemo,
    display_name: str,
    handle: str,
    stage: DealStage,
    proofs: list[DeliverableProof],
    approved: DeliverableProof | None,
    payment: PaymentStatus | None,
    today: date,
    readings: dict[uuid.UUID, list[ProofFileReading]],
    seal: Seal,
) -> DealLine:
    first_submitted_on = (
        india_date(min(proof.created_at for proof in proofs)) if proofs else None
    )
    on_time = (
        None
        if first_submitted_on is None or memo.content_due_on is None
        else first_submitted_on <= memo.content_due_on
    )
    approved_on = _approved_on(memo, approved, proofs)
    if payment is None and approved_on is not None:
        payment = _payment_not_yet_written(memo, approved_on)
    paid_on_time = (
        None
        if payment is None or payment.marked_paid_at is None
        else india_date(payment.marked_paid_at) <= payment.due_on
    )
    return DealLine(
        memo=memo,
        creator_display_name=display_name,
        creator_handle=handle,
        stage=stage,
        first_submitted_on=first_submitted_on,
        delivered_on_time=on_time,
        approved_on=approved_on,
        approved_by_clock=approved is not None
        and (approved.auto_approved or approved.status == "submitted"),
        content_url=approved.content_url if approved is not None else None,
        disclosure_confirmed=(
            approved.disclosure_confirmed if approved is not None else None
        ),
        payment=payment,
        payment_state=(
            None
            if payment is None
            else payments.derive_state(
                payment, today, has_open_dispute=stage.has_open_dispute
            )
        ),
        paid_on_time=paid_on_time,
        results=_results(readings.get(approved.id, []) if approved is not None else []),
        seal=seal,
    )


def _approved_on(
    memo: DealMemo, approved: DeliverableProof | None, proofs: list[DeliverableProof]
) -> date | None:
    """When the work was approved. By the clock, that is its deadline, as when
    the approval is written down (`proof_service.settle_if_overdue`)."""
    if approved is None:
        return None
    if approved.approved_at is not None:
        return india_date(approved.approved_at)
    return india_date(approval_deadline(memo, approved, proofs))


def _payment_not_yet_written(memo: DealMemo, approved_on: date) -> PaymentStatus | None:
    """The payment a clock approval has opened but nobody has written down yet.

    Approval by the clock is written lazily, when someone next opens the
    proof (`proof_service.settle_if_overdue`), and the payment record with
    it. Until then the deal is at Payment with no row. The report works the
    row out as `payment_status.service.open_on_approval` will write it, so a
    report never depends on whether anyone happened to look. Never added to
    the session: nothing is written by a read.
    """
    if memo.fee_amount_paise is None:
        return None  # barter: nothing to pay (D-026)
    return PaymentStatus(
        deal_memo_id=memo.id,
        amount_paise=memo.fee_amount_paise,
        currency=memo.currency,
        due_on=payments.due_date_for(approved_on, memo.payment_due_days),
    )


def _results(readings: list[ProofFileReading]) -> Results:
    counted = [r for r in readings if r.creator_marked_at is None]
    numbers: dict[str, int | None] = {}
    for metric in READING_METRICS:
        shown = [value for r in counted if (value := getattr(r, metric)) is not None]
        numbers[metric] = sum(shown) if shown else None
    return Results(
        readings=len(counted),
        readings_marked_wrong=len(readings) - len(counted),
        includes_abbreviated=any(r.abbreviated for r in counted),
        numbers=numbers,
    )


# --- the campaign ------------------------------------------------------------------------


def _sum_results(parts: list[Results]) -> Results:
    numbers: dict[str, int | None] = {}
    for metric in READING_METRICS:
        shown = [value for part in parts if (value := part.numbers[metric]) is not None]
        numbers[metric] = sum(shown) if shown else None
    return Results(
        readings=sum(part.readings for part in parts),
        readings_marked_wrong=sum(part.readings_marked_wrong for part in parts),
        includes_abbreviated=any(part.includes_abbreviated for part in parts),
        numbers=numbers,
    )


def _totals(lines: list[DealLine], applications: dict[str, int]) -> Totals:
    agreed = [line for line in lines if line.stage.stage in AGREED_STAGES]
    delivered = [line for line in lines if line.delivered_on_time is not None]
    paid = [line for line in lines if line.paid_on_time is not None]
    return Totals(
        applications=applications,
        deals=len(lines),
        deals_agreed=len(agreed),
        deals_finished=sum(1 for line in lines if line.stage.stage == FINISHED),
        barter_deals_agreed=sum(1 for line in agreed if not line.memo.fee_amount_paise),
        agreed_value_paise=sum(line.memo.fee_amount_paise or 0 for line in agreed),
        marked_paid_paise=sum(
            line.payment.amount_paise
            for line in lines
            if line.payment is not None and line.payment.marked_paid_at is not None
        ),
        confirmed_paise=sum(
            line.payment.amount_paise
            for line in lines
            if line.payment is not None and line.payment.confirmed_at is not None
        ),
        deliveries_judged=len(delivered),
        delivered_on_time=sum(1 for line in delivered if line.delivered_on_time),
        payments_sent=len(paid),
        payments_sent_on_time=sum(1 for line in paid if line.paid_on_time),
        results=_sum_results([line.results for line in lines]),
        records_intact=all(line.seal.intact for line in lines),
    )
