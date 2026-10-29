"""Drafts shown to the brand before posting (item 27, D-140).

On a memo whose agreed terms say `draft_review`, the creator shows a draft
(the caption or script, a link, a note) and the brand approves it or asks
for changes, within the memo's approval window, on proof's own clock
(D-025, `review_clock`): silence approves, so a brand that goes quiet
cannot hold the creator up. Proof waits for an approved draft
(`proof_service.submit_proof`), and records which draft it follows, so
what was approved can be held up against what was posted.

Each draft and each answer is sealed onto the deal record by its
fingerprints; the record never holds the words themselves. A draft may carry
images (piece 2), uploaded and cleaned exactly as proof files are (D-065):
their fingerprints are sealed with the draft, and a brand only ever opens
the cleaned copies. Approval by the
clock needs no job: it is settled whenever a draft is read or acted on, as
proof's is.
"""

import uuid
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import exists, inspect, select
from sqlalchemy.orm import Session

from app.core.errors import DomainError
from app.core.export import MAX_ROWS_PER_SECTION, ExportedSection, allow, build_section
from app.core.storage import FileStore
from app.modules.deal_memo import proof_file_service
from app.modules.deal_memo import record_service as record
from app.modules.deal_memo.draft_models import ContentDraft
from app.modules.deal_memo.draft_rules import agreed_at, answer_deadline, approved_among
from app.modules.deal_memo.exceptions import (
    DraftAlreadyDecided,
    DraftImagesNotReady,
    DraftNotFound,
    DraftReviewNotAgreed,
    MemoStatusConflict,
)
from app.modules.deal_memo.models import DealMemo
from app.modules.deal_memo.proof_models import DeliverableProof, ProofFile
from app.modules.deal_memo.service import _notify_other_side, memos_for_account

EXPORTED_TABLES = frozenset({"content_draft"})


def drafts_of(db: Session, memo: DealMemo) -> list[ContentDraft]:
    """Every draft on the memo, oldest first. One query."""
    return list(
        db.scalars(
            select(ContentDraft)
            .where(ContentDraft.deal_memo_id == memo.id)
            .order_by(ContentDraft.round)
        ).all()
    )


def files_by_draft(
    db: Session, drafts: Sequence[ContentDraft]
) -> dict[uuid.UUID, list[ProofFile]]:
    """Each draft's images, in the order the creator chose. One query for them all."""
    found: dict[uuid.UUID, list[ProofFile]] = {draft.id: [] for draft in drafts}
    if found:
        for file in db.scalars(
            select(ProofFile)
            .where(ProofFile.draft_id.in_(list(found)))
            .order_by(ProofFile.draft_id, ProofFile.position)
        ).all():
            if file.draft_id is not None:
                found[file.draft_id].append(file)
    return found


def request_upload(
    db: Session,
    store: FileStore,
    memo: DealMemo,
    uploader_account_id: uuid.UUID,
    *,
    content_type: str,
    size_bytes: int,
    sha256: str,
    now: datetime,
) -> proof_file_service.RequestedUpload:
    """A pending image for a draft, and the signed form to upload it. Commits.

    Only where a draft can still be shown: the terms include draft review
    and no draft is approved yet. Raises DraftReviewNotAgreed and
    DraftAlreadyDecided; the upload's own rules (an accepted memo, the cap on
    unfinished uploads) are proof's, in `proof_file_service.request_upload`,
    which locks the memo. Showing the draft checks all of this again under
    the lock, so an upload asked for at the moment a draft is approved can
    never join it.
    """
    if not memo.draft_review:
        raise DraftReviewNotAgreed()
    if approved_among(memo, drafts_of(db, memo), now) is not None:
        db.rollback()
        raise DraftAlreadyDecided("A draft is already approved; post the work.")
    return proof_file_service.request_upload(
        db,
        store,
        memo,
        uploader_account_id,
        content_type=content_type,
        size_bytes=size_bytes,
        sha256=sha256,
        now=now,
        purpose="draft",
    )


def submit_draft(
    db: Session,
    memo: DealMemo,
    fields: dict[str, Any],
    now: datetime,
    *,
    store: FileStore | None = None,
    file_ids: Sequence[uuid.UUID] = (),
    uploader_account_id: uuid.UUID | None = None,
) -> ContentDraft:
    """Show the brand a draft, with any images already uploaded. Commits.

    The memo's row is locked and read again first, so two drafts at once
    cannot both find nothing waiting. A draft is work, so it marks that
    work has started, as proof does (D-026). Raises MemoStatusConflict
    unless the memo is accepted, DraftReviewNotAgreed when its terms have
    no draft review, and DraftAlreadyDecided while one waits or once one is
    approved; and, for images, ProofFileNotFound for one that is not this
    creator's pending upload on this deal and ProofFileNotUploaded for one
    that never finished uploading.
    """
    if file_ids and (store is None or uploader_account_id is None):
        raise ValueError("images need the store and the uploader")
    db.scalars(
        select(DealMemo)
        .where(DealMemo.id == memo.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).one()
    if memo.status != "accepted":
        db.rollback()
        raise MemoStatusConflict("A draft can only be shown on an accepted memo.")
    if not memo.draft_review:
        db.rollback()
        raise DraftReviewNotAgreed()
    drafts = drafts_of(db, memo)
    if approved_among(memo, drafts, now) is not None:
        db.rollback()
        raise DraftAlreadyDecided("A draft is already approved; post the work.")
    if any(draft.status == "submitted" for draft in drafts):
        db.rollback()
        raise DraftAlreadyDecided("A draft is already waiting for the brand.")

    draft = ContentDraft(
        deal_memo_id=memo.id,
        round=len(drafts) + 1,
        status="submitted",
        created_at=now,
        updated_at=now,
        **fields,
    )
    db.add(draft)
    db.flush()  # the record names the draft, so it needs its id
    files: list[ProofFile] = []
    if file_ids and store is not None and uploader_account_id is not None:
        try:
            files = proof_file_service.attach(
                db, store, memo, list(file_ids), uploader_account_id, now, draft=draft
            )
        except DomainError:
            db.rollback()
            raise
    # Ready at once without images; with them, once the cleaner has been
    # through every one (proof_cleaning_service).
    draft.images_ready_at = None if files else now
    record.append(
        db,
        memo,
        kind="draft_submitted",
        actor_role="creator",
        now=now,
        facts={
            "draft_id": str(draft.id),
            "round": draft.round,
            "body_sha256": record.fingerprint(draft.body),
            "content_url_sha256": (
                record.fingerprint(draft.content_url) if draft.content_url else None
            ),
            "note_sha256": record.fingerprint(draft.note) if draft.note else None,
            # Only when there are images, so a draft without any is sealed
            # exactly as before piece 2.
            **({"files": proof_file_service.record_facts(files)} if files else {}),
        },
    )
    if memo.work_started_at is None:
        memo.work_started_at = now
        memo.updated_at = now
    _notify_other_side(db, memo, to="brand", notification_type="draft_submitted", now=now)
    db.commit()
    db.refresh(draft)
    return draft


def settle_if_overdue(
    db: Session,
    memo: DealMemo,
    draft: ContentDraft,
    now: datetime,
    history: Sequence[ContentDraft] | None = None,
) -> ContentDraft:
    """Approve a draft whose window has passed, and say so. Commits only then.

    Called whenever a draft is read or acted on, so the outcome never waits
    for a scheduled job. It took effect at the deadline and is recorded now,
    when it was noticed; the record shows both. Only if the deal was still
    agreed at the deadline: a draft left waiting when the deal was cancelled
    is never approved, but one whose deadline passed before a later
    cancellation was approved then, and the record says so.

    The memo is locked and both rows read again before anything is written,
    in the same order as an answer takes them, so an answer or a
    cancellation that landed meanwhile is never overwritten.
    """
    if draft.status != "submitted" or memo.status not in ("accepted", "cancelled"):
        return draft
    deadline = answer_deadline(
        memo, draft, history if history is not None else drafts_of(db, memo)
    )
    if deadline is None or now < deadline or not agreed_at(memo, deadline):
        return draft  # no clock yet while its images are being cleaned
    db.scalars(
        select(DealMemo)
        .where(DealMemo.id == memo.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).one()
    db.refresh(draft, with_for_update=True)
    if draft.status != "submitted" or not agreed_at(memo, deadline):
        db.rollback()  # answered or cancelled meanwhile: theirs stands
        return draft
    draft.status = "approved"
    draft.approved_at = deadline
    draft.answered_at = deadline
    draft.auto_approved = True
    draft.updated_at = now
    record.append(
        db,
        memo,
        kind="draft_auto_approved",
        actor_role="system",
        now=now,
        occurred_at=deadline,
        facts={"draft_id": str(draft.id)},
    )
    if memo.status == "accepted":  # nothing to act on once the deal has ended
        _notify_other_side(
            db, memo, to="creator", notification_type="draft_auto_approved", now=now
        )
    db.commit()
    db.refresh(draft)
    return draft


def approve_draft(
    db: Session, memo: DealMemo, draft: ContentDraft, now: datetime
) -> ContentDraft:
    """The brand approves the draft. Commits.

    Raises MemoStatusConflict once the deal is no longer agreed,
    DraftAlreadyDecided once the draft is answered, and
    DraftImagesNotReady while any of its images is still being cleaned:
    nothing is approved that the brand could not open.
    """
    _lock_for_answer(db, memo, draft)
    settle_if_overdue(db, memo, draft, now)
    if draft.status != "submitted":
        db.rollback()
        raise DraftAlreadyDecided()
    if draft.images_ready_at is None:
        db.rollback()
        raise DraftImagesNotReady()
    draft.status = "approved"
    draft.approved_at = now
    draft.answered_at = now
    draft.updated_at = now
    record.append(
        db,
        memo,
        kind="draft_approved",
        actor_role="brand",
        now=now,
        facts={"draft_id": str(draft.id)},
    )
    _notify_other_side(
        db, memo, to="creator", notification_type="draft_approved", now=now
    )
    db.commit()
    db.refresh(draft)
    return draft


def request_changes(
    db: Session, memo: DealMemo, draft: ContentDraft, note: str, now: datetime
) -> ContentDraft:
    """The brand asks for changes, so the creator shows a new draft. Commits.

    Raises MemoStatusConflict once the deal is no longer agreed, and
    DraftAlreadyDecided once the draft is answered, by the brand or by the
    clock.
    """
    _lock_for_answer(db, memo, draft)
    settle_if_overdue(db, memo, draft, now)
    if draft.status != "submitted":
        db.rollback()
        raise DraftAlreadyDecided()
    draft.status = "changes_requested"
    draft.changes_note = note
    draft.answered_at = now
    draft.updated_at = now
    record.append(
        db,
        memo,
        kind="draft_changes_requested",
        actor_role="brand",
        now=now,
        facts={"draft_id": str(draft.id), "note_sha256": record.fingerprint(note)},
    )
    _notify_other_side(
        db, memo, to="creator", notification_type="draft_changes_requested", now=now
    )
    db.commit()
    db.refresh(draft)
    return draft


def _lock_for_answer(db: Session, memo: DealMemo, draft: ContentDraft) -> None:
    """Lock the memo, then the draft, and check the deal is still agreed.

    The memo first, as showing a draft and submitting proof take it, so an
    answer and a proof at the same moment run one after the other: a proof
    never names a draft the brand sent back in the same instant. Raises
    MemoStatusConflict.
    """
    db.scalars(
        select(DealMemo)
        .where(DealMemo.id == memo.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).one()
    if memo.status != "accepted":
        db.rollback()
        raise MemoStatusConflict("Only a draft on an agreed deal can be answered.")
    # Proof exists only once a draft is approved. An answer that waited for
    # the lock behind a proof read its clock before the proof: it is too late.
    if db.scalar(select(exists().where(DeliverableProof.deal_memo_id == memo.id))):
        db.rollback()
        raise DraftAlreadyDecided("Proof already follows the approved draft.")
    db.refresh(draft, attribute_names=["status"], with_for_update=True)


def list_for_memo(db: Session, memo: DealMemo, now: datetime) -> list[ContentDraft]:
    """Every draft on the memo, newest first, settled if overdue.

    One query, and a fixed few more only when a draft is settled: settling
    commits or rolls back, which expires every row loaded, so they are read
    again in one query rather than one at a time.
    """
    drafts = drafts_of(db, memo)
    for draft in [d for d in drafts if d.status == "submitted"]:
        settle_if_overdue(db, memo, draft, now, history=drafts)
    if inspect(memo).expired or any(inspect(d).expired for d in drafts):
        drafts = drafts_of(db, memo)
    return sorted(drafts, key=lambda d: (d.created_at, d.id), reverse=True)


def get_for_memo(
    db: Session, memo: DealMemo, draft_id: uuid.UUID, now: datetime
) -> ContentDraft:
    """One of the memo's drafts, settled if overdue. Raises DraftNotFound."""
    draft = db.scalars(
        select(ContentDraft).where(
            ContentDraft.id == draft_id, ContentDraft.deal_memo_id == memo.id
        )
    ).first()
    if draft is None:
        raise DraftNotFound()
    return settle_if_overdue(db, memo, draft, now)


# Everything a person reads of a draft, both sides alike: what was shown,
# what was asked and when it was answered.
EXPORT_FIELDS = allow(
    "id",
    "deal_memo_id",
    "round",
    "body",
    "content_url",
    "note",
    "status",
    "changes_note",
    "approved_at",
    "answered_at",
    "auto_approved",
    "images_ready_at",
    "created_at",
    "updated_at",
)


def export_for_account(db: Session, account_id: uuid.UUID) -> list[ExportedSection]:
    """The drafts on every deal this account is a party to, both sides alike."""
    memo_ids = [
        m.id for m in memos_for_account(db, account_id, limit=MAX_ROWS_PER_SECTION + 1)
    ]
    drafts: list[ContentDraft] = []
    if memo_ids:
        drafts = list(
            db.scalars(
                select(ContentDraft)
                .where(ContentDraft.deal_memo_id.in_(memo_ids))
                .order_by(ContentDraft.created_at, ContentDraft.id)
                .limit(MAX_ROWS_PER_SECTION + 1)
            ).all()
        )
    return [
        build_section(
            "content_drafts",
            table="content_draft",
            purpose=(
                "Drafts shown before posting on those deals, and each answer: "
                "approved, approved by the clock, or changes asked (item 27)."
            ),
            objects=drafts,
            fields=EXPORT_FIELDS,
        )
    ]
