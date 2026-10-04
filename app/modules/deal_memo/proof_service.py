"""Proof rules (D-024, D-025).

Auto-approval needs no scheduled job: whenever anyone touches a submission we
check whether its window has passed and settle it then. A job can send the
day-3 reminder later, but the outcome never waits for one.
"""

import uuid
from collections.abc import Sequence
from datetime import date, datetime, time, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import IST, india_date
from app.core.errors import DomainError
from app.core.storage import FileStore
from app.modules.deal_memo import proof_file_service
from app.modules.deal_memo import record_service as record
from app.modules.deal_memo.exceptions import (
    MemoStatusConflict,
    ProofAlreadyDecided,
    ProofNeedsEvidence,
    ProofNotFound,
)
from app.modules.deal_memo.models import DealMemo
from app.modules.deal_memo.proof_models import DeliverableProof
from app.modules.deal_memo.service import _notify_other_side
from app.modules.payment_status import service as payments


def submit_proof(
    db: Session,
    memo: DealMemo,
    fields: dict[str, Any],
    now: datetime,
    *,
    store: FileStore | None = None,
    file_ids: Sequence[uuid.UUID] = (),
    uploader_account_id: uuid.UUID | None = None,
) -> DeliverableProof:
    """Record the creator's evidence, and mark that work has started.

    Evidence is a link, files (D-065), or both; never neither. Files are
    attached in the same transaction as the proof, so a proof never exists
    with half its files.

    Raises MemoStatusConflict unless the memo is accepted, and
    ProofAlreadyDecided while another submission waits for review.

    The memo's row is locked and read again first: two submissions at once
    would otherwise both find nothing waiting, and the database's rule of one
    open submission would refuse the second as a raw error, a 500. Locked,
    the second waits, then sees the first, or a memo cancelled meanwhile.
    """
    db.scalars(
        select(DealMemo)
        .where(DealMemo.id == memo.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).one()
    if memo.status != "accepted":
        db.rollback()
        raise MemoStatusConflict("Proof can only be submitted for an accepted memo.")

    open_submission = db.scalars(
        select(DeliverableProof).where(
            DeliverableProof.deal_memo_id == memo.id,
            DeliverableProof.status == "submitted",
        )
    ).first()
    if open_submission is not None:
        db.rollback()
        raise ProofAlreadyDecided("This memo already has proof waiting for review.")

    if not fields.get("content_url") and not file_ids:
        db.rollback()
        raise ProofNeedsEvidence()
    if file_ids and (store is None or uploader_account_id is None):
        raise ValueError("attaching files needs the store and the uploader")

    proof = DeliverableProof(
        deal_memo_id=memo.id,
        status="submitted",
        created_at=now,
        updated_at=now,
        **fields,
    )
    db.add(proof)
    db.flush()  # the record names the submission, so it needs its id
    files = []
    if file_ids and store is not None and uploader_account_id is not None:
        try:
            files = proof_file_service.attach(
                db, store, memo, proof, list(file_ids), uploader_account_id, now
            )
        except DomainError:
            db.rollback()
            raise
    # The link and note are typed, so the record keeps their fingerprints.
    record.append(
        db,
        memo,
        kind="proof_submitted",
        actor_role="creator",
        now=now,
        facts={
            "proof_id": str(proof.id),
            "format": proof.format,
            "disclosure_confirmed": proof.disclosure_confirmed,
            "content_url_sha256": (
                record.fingerprint(proof.content_url) if proof.content_url else None
            ),
            "note_sha256": record.fingerprint(proof.note) if proof.note else None,
            # Each file as declared and as S3 enforced it on upload (D-065).
            # Only when there are files, so a link-only entry reads as before.
            **({"files": proof_file_service.record_facts(files)} if files else {}),
        },
    )
    # The line between a cancellation that counts and one that does not (D-026).
    if memo.work_started_at is None:
        memo.work_started_at = now
        memo.updated_at = now
    _notify_other_side(db, memo, to="brand", notification_type="proof_submitted", now=now)
    db.commit()
    db.refresh(proof)
    return proof


def review_clock_start(
    proof: DeliverableProof, history: Sequence[DeliverableProof]
) -> datetime:
    """When this submission's review clock started (D-025).

    The first submission starts a clock, and so does the one that follows
    the brand's first request for changes. Any later resubmission runs on
    the clock that first request restarted: asking again does not buy the
    brand more time. `history` is every submission on the memo, in any order.
    """
    key = (proof.created_at, proof.id)
    earlier = sorted(
        (p for p in history if (p.created_at, p.id) < key),
        key=lambda p: (p.created_at, p.id),
    )
    if len(earlier) <= 1:
        return proof.created_at
    return earlier[1].created_at


def approval_deadline(
    memo: DealMemo, proof: DeliverableProof, history: Sequence[DeliverableProof]
) -> datetime:
    """When an unreviewed submission approves itself (D-025).

    Counted in whole Tamil Nadu calendar days, as D-025 says: the window
    ends at midnight IST after its last full day, so proof sent at 23:00
    loses nothing to proof sent at 00:30 the same day. `history` is required
    on purpose: without it a resubmission cannot be told from a first one.
    """
    last_day = approval_last_day(memo, proof, history)
    return datetime.combine(last_day + timedelta(days=1), time.min, tzinfo=IST)


def approval_last_day(
    memo: DealMemo, proof: DeliverableProof, history: Sequence[DeliverableProof]
) -> date:
    """The last whole day the brand has to decide, in Tamil Nadu (D-025).

    What a person is told ("decide by 24 Sep"): the deadline itself is the
    midnight that ends this day, which would read as the day after.
    """
    first_day = india_date(review_clock_start(proof, history))
    return first_day + timedelta(days=memo.approval_window_days)


def _history(db: Session, memo: DealMemo) -> list[DeliverableProof]:
    return list(
        db.scalars(
            select(DeliverableProof).where(DeliverableProof.deal_memo_id == memo.id)
        ).all()
    )


def settle_if_overdue(
    db: Session,
    memo: DealMemo,
    proof: DeliverableProof,
    now: datetime,
    history: Sequence[DeliverableProof] | None = None,
) -> DeliverableProof:
    """Approve a submission whose window has passed, and say so.

    Called whenever a submission is read or acted on, so the outcome never
    depends on a scheduled job having run. Pass `history` when the memo's
    submissions are already loaded; otherwise they are read here.
    """
    if proof.status != "submitted":
        return proof
    deadline = approval_deadline(
        memo, proof, history if history is not None else _history(db, memo)
    )
    if now >= deadline:
        proof.status = "approved"
        proof.approved_at = deadline
        proof.auto_approved = True
        proof.updated_at = now
        # Took effect at the deadline; recorded now, when it was noticed. The
        # record shows both rather than pretending we saw it at the time.
        record.append(
            db,
            memo,
            kind="proof_auto_approved",
            actor_role="system",
            now=now,
            occurred_at=proof.approved_at,
            facts={"proof_id": str(proof.id)},
        )
        _notify_other_side(
            db, memo, to="creator", notification_type="proof_auto_approved", now=now
        )
        # Approval is what starts the payment clock (D-027). Opened here, in
        # the same transaction, so a memo can never be approved without the
        # payment it is owed existing.
        payments.open_on_approval(db, memo, approved_at=proof.approved_at, now=now)
        db.commit()
        db.refresh(proof)
    return proof


def approve_proof(
    db: Session, memo: DealMemo, proof: DeliverableProof, now: datetime
) -> DeliverableProof:
    """The brand approves. Raises ProofAlreadyDecided if it is settled."""
    settle_if_overdue(db, memo, proof, now)
    if proof.status != "submitted":
        db.rollback()
        raise ProofAlreadyDecided()

    proof.status = "approved"
    proof.approved_at = now
    proof.updated_at = now
    record.append(
        db,
        memo,
        kind="proof_approved",
        actor_role="brand",
        now=now,
        facts={"proof_id": str(proof.id)},
    )
    _notify_other_side(
        db, memo, to="creator", notification_type="proof_approved", now=now
    )
    payments.open_on_approval(db, memo, approved_at=now, now=now)
    db.commit()
    db.refresh(proof)
    return proof


def request_revision(
    db: Session, memo: DealMemo, proof: DeliverableProof, note: str, now: datetime
) -> DeliverableProof:
    """The brand asks for a change, which lets the creator submit again."""
    settle_if_overdue(db, memo, proof, now)
    if proof.status != "submitted":
        db.rollback()
        raise ProofAlreadyDecided()

    proof.status = "revision_requested"
    proof.revision_note = note
    proof.updated_at = now
    record.append(
        db,
        memo,
        kind="proof_revision_requested",
        actor_role="brand",
        now=now,
        facts={"proof_id": str(proof.id), "note_sha256": record.fingerprint(note)},
    )
    _notify_other_side(
        db, memo, to="creator", notification_type="proof_revision_requested", now=now
    )
    db.commit()
    db.refresh(proof)
    return proof


def list_for_memo(db: Session, memo: DealMemo, now: datetime) -> list[DeliverableProof]:
    """Every submission for a memo, newest first, settled if overdue."""
    proofs = list(
        db.scalars(
            select(DeliverableProof)
            .where(DeliverableProof.deal_memo_id == memo.id)
            .order_by(DeliverableProof.created_at.desc())
        ).all()
    )
    for proof in proofs:
        settle_if_overdue(db, memo, proof, now, history=proofs)
    return proofs


def get_for_memo(
    db: Session, memo: DealMemo, proof_id: uuid.UUID, now: datetime
) -> DeliverableProof:
    proof = db.scalars(
        select(DeliverableProof).where(
            DeliverableProof.id == proof_id, DeliverableProof.deal_memo_id == memo.id
        )
    ).first()
    if proof is None:
        raise ProofNotFound()
    return settle_if_overdue(db, memo, proof, now)
