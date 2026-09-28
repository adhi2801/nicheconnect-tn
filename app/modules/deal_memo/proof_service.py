"""Proof rules (D-024, D-025).

Auto-approval needs no scheduled job: whenever anyone touches a submission we
check whether its window has passed and settle it then. A job can send the
day-3 reminder later, but the outcome never waits for one.
"""

import uuid
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.deal_memo import record_service as record
from app.modules.deal_memo.exceptions import (
    MemoStatusConflict,
    ProofAlreadyDecided,
    ProofNotFound,
)
from app.modules.deal_memo.models import DealMemo
from app.modules.deal_memo.proof_models import DeliverableProof
from app.modules.deal_memo.service import _notify_other_side
from app.modules.payment_status import service as payments


def submit_proof(
    db: Session, memo: DealMemo, fields: dict[str, Any], now: datetime
) -> DeliverableProof:
    """Record the creator's evidence, and mark that work has started.

    Raises MemoStatusConflict unless the memo is accepted, and
    ProofNotSubmitted-free: a second open submission is refused by the database.
    """
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

    proof = DeliverableProof(
        deal_memo_id=memo.id,
        status="submitted",
        created_at=now,
        updated_at=now,
        **fields,
    )
    db.add(proof)
    db.flush()  # the record names the submission, so it needs its id
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
            "content_url_sha256": record.fingerprint(proof.content_url),
            "note_sha256": record.fingerprint(proof.note) if proof.note else None,
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


def approval_deadline(memo: DealMemo, proof: DeliverableProof) -> datetime:
    """When an unreviewed submission approves itself (D-025)."""
    return proof.created_at + timedelta(days=memo.approval_window_days)


def settle_if_overdue(
    db: Session, memo: DealMemo, proof: DeliverableProof, now: datetime
) -> DeliverableProof:
    """Approve a submission whose window has passed, and say so.

    Called whenever a submission is read or acted on, so the outcome never
    depends on a scheduled job having run.
    """
    if proof.status == "submitted" and now >= approval_deadline(memo, proof):
        proof.status = "approved"
        proof.approved_at = approval_deadline(memo, proof)
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
        settle_if_overdue(db, memo, proof, now)
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
