"""Drafts shown to the brand before posting (item 27, D-140).

On a memo whose agreed terms say `draft_review`, the creator shows a draft
(the caption or script, a link, a note) and the brand approves it or asks
for changes, within the memo's approval window, on proof's own clock
(D-025, `review_clock`): silence approves, so a brand that goes quiet
cannot hold the creator up. Proof waits for an approved draft
(`proof_service.submit_proof`), and records which draft it follows, so
what was approved can be held up against what was posted.

Each draft and each answer is sealed onto the deal record by its
fingerprints; the record never holds the words themselves. Approval by the
clock needs no job: it is settled whenever a draft is read or acted on, as
proof's is.
"""

import uuid
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.export import MAX_ROWS_PER_SECTION, ExportedSection, allow, build_section
from app.modules.deal_memo import record_service as record
from app.modules.deal_memo.draft_models import ContentDraft
from app.modules.deal_memo.draft_rules import approved_among
from app.modules.deal_memo.exceptions import (
    DraftAlreadyDecided,
    DraftNotFound,
    DraftReviewNotAgreed,
    MemoStatusConflict,
)
from app.modules.deal_memo.models import DealMemo
from app.modules.deal_memo.review_clock import approval_deadline
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


def submit_draft(
    db: Session, memo: DealMemo, fields: dict[str, Any], now: datetime
) -> ContentDraft:
    """Show the brand a draft. Commits.

    The memo's row is locked and read again first, so two drafts at once
    cannot both find nothing waiting. A draft is work, so it marks that
    work has started, as proof does (D-026). Raises MemoStatusConflict
    unless the memo is accepted, DraftReviewNotAgreed when its terms have
    no draft review, and DraftAlreadyDecided while one waits or once one is
    approved.
    """
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
    when it was noticed; the record shows both.
    """
    if draft.status != "submitted":
        return draft
    deadline = approval_deadline(
        memo, draft, history if history is not None else drafts_of(db, memo)
    )
    if now < deadline:
        return draft
    draft.status = "approved"
    draft.approved_at = deadline
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
    _notify_other_side(
        db, memo, to="creator", notification_type="draft_auto_approved", now=now
    )
    db.commit()
    db.refresh(draft)
    return draft


def approve_draft(
    db: Session, memo: DealMemo, draft: ContentDraft, now: datetime
) -> ContentDraft:
    """The brand approves the draft. Commits. Raises DraftAlreadyDecided."""
    # Locked and read again before the check, so an approval and a request
    # for changes at once cannot both pass it.
    db.refresh(draft, attribute_names=["status"], with_for_update=True)
    settle_if_overdue(db, memo, draft, now)
    if draft.status != "submitted":
        db.rollback()
        raise DraftAlreadyDecided()
    draft.status = "approved"
    draft.approved_at = now
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

    Raises DraftAlreadyDecided once the draft is answered, by the brand or
    by the clock.
    """
    db.refresh(draft, attribute_names=["status"], with_for_update=True)
    settle_if_overdue(db, memo, draft, now)
    if draft.status != "submitted":
        db.rollback()
        raise DraftAlreadyDecided()
    draft.status = "changes_requested"
    draft.changes_note = note
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


def list_for_memo(db: Session, memo: DealMemo, now: datetime) -> list[ContentDraft]:
    """Every draft on the memo, newest first, settled if overdue. Two queries."""
    drafts = drafts_of(db, memo)
    for draft in drafts:
        settle_if_overdue(db, memo, draft, now, history=drafts)
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
    "auto_approved",
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
