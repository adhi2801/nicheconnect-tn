"""Feedback on a finished deal (item 77, D-136): giving it, reading it, the figures.

A deal finishes when its payment is confirmed, or, for barter, when its work
is approved (D-026; approval by the clock is settled first, D-025). From
then each side may answer once within 14 days (`feedback_rules`). The answer
and its `feedback_given` record entry, carrying its fingerprint, are written
in one transaction under the deal's lock; the other side is told that an
answer exists, never what it says.

Nobody sees an answer until both sides answered or the window closed: not
the other side, not the profile figures, not the notes list, not even the
other side's export. A person always sees their own.

Threat model: only the deal's two parties give or read a deal's feedback
(`dependencies.visible_memo_for_account`, 404 to anyone else); notes are
plain text, a brand's flagged for fee requests; 50 answers a day per
account; a pumped record built with one partner reads as one partner
(`counterparties`); nothing can be edited or removed, so nothing can be
quietly buried.
"""

import json
import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy import ColumnElement, Select, exists, func, or_, select
from sqlalchemy.orm import Session, aliased

from app.core.export import MAX_ROWS_PER_SECTION, ExportedSection, allow, build_section
from app.core.pagination import Slice, build_slice, older_than_cursor
from app.modules.campaigns.models import Application, Campaign
from app.modules.deal_memo import proof_service
from app.modules.deal_memo import record_service as record
from app.modules.deal_memo.exceptions import FeedbackClosed
from app.modules.deal_memo.feedback_models import DealFeedback
from app.modules.deal_memo.feedback_rules import (
    MIN_ANSWERS,
    SCORES,
    may_answer,
    revealed,
    window_ends,
)
from app.modules.deal_memo.models import DealMemo
from app.modules.deal_memo.service import memos_for_account, notify_party
from app.modules.payment_status.models import PaymentStatus

EXPORTED_TABLES = frozenset({"deal_feedback"})
EXPORT_FIELDS = allow(
    "id",
    "deal_memo_id",
    "author_side",
    "brief",
    "reliability",
    "easy",
    "note",
    "window_ends_at",
    "created_at",
)
OTHER = {"brand": "creator", "creator": "brand"}


@dataclass(frozen=True)
class FeedbackView:
    """A deal's feedback as one side sees it."""

    window_ends_at: datetime | None
    open: bool
    mine: DealFeedback | None
    # The other side's, only once revealed.
    theirs: DealFeedback | None


@dataclass(frozen=True)
class Figures:
    answers: int
    counterparties: int
    # Averages, None below MIN_ANSWERS: not enough to say, never zero.
    brief: float | None
    reliability: float | None
    easy: float | None


@dataclass(frozen=True)
class NoteAbout:
    feedback: DealFeedback
    # What the person the note is about said on the same deal, if anything.
    reply: str | None


def finished_at(db: Session, memo: DealMemo, now: datetime) -> datetime | None:
    """When the deal finished, or None if it has not."""
    if memo.status != "accepted":
        return None
    proofs = proof_service.list_for_memo(db, memo, now)
    approved = [p.approved_at for p in proofs if p.status == "approved" and p.approved_at]
    if not approved:
        return None
    if not memo.fee_amount_paise:
        return min(approved)  # barter: done when its work is approved (D-026)
    payment = db.scalars(
        select(PaymentStatus).where(PaymentStatus.deal_memo_id == memo.id)
    ).first()
    return payment.confirmed_at if payment is not None else None


def _of(db: Session, memo: DealMemo) -> dict[str, DealFeedback]:
    return {
        f.author_side: f
        for f in db.scalars(
            select(DealFeedback).where(DealFeedback.deal_memo_id == memo.id)
        )
    }


def view(db: Session, memo: DealMemo, side: str, now: datetime) -> FeedbackView:
    """The deal's feedback as `side` may see it now."""
    done = finished_at(db, memo, now)
    answers = _of(db, memo)
    mine, theirs = answers.get(side), answers.get(OTHER[side])
    shown = (
        theirs
        if theirs is not None and revealed(mine is not None, theirs.window_ends_at, now)
        else None
    )
    return FeedbackView(
        window_ends_at=window_ends(done) if done is not None else None,
        open=may_answer(done, mine is not None, now) is None,
        mine=mine,
        theirs=shown,
    )


def give(
    db: Session,
    memo: DealMemo,
    side: str,
    scores: dict[str, int],
    note: str | None,
    now: datetime,
) -> DealFeedback:
    """Answer once, seal it, tell the other side. Commits. Raises FeedbackClosed."""
    db.refresh(memo, attribute_names=["status"], with_for_update=True)
    done = finished_at(db, memo, now)
    answered = db.scalar(
        select(DealFeedback.id).where(
            DealFeedback.deal_memo_id == memo.id, DealFeedback.author_side == side
        )
    )
    reason = may_answer(done, answered is not None, now)
    if reason is not None or done is None:
        db.rollback()
        raise FeedbackClosed.because(reason or "not_finished")
    feedback = DealFeedback(
        deal_memo_id=memo.id,
        author_side=side,
        note=note,
        window_ends_at=window_ends(done),
        created_at=now,
        **{name: scores[name] for name in SCORES},
    )
    db.add(feedback)
    db.flush()
    record.append(
        db,
        memo,
        kind="feedback_given",
        actor_role=side,
        now=now,
        facts={"feedback_id": str(feedback.id), "feedback_sha256": fingerprint(feedback)},
    )
    notify_party(db, memo, to=OTHER[side], notification_type="feedback_received", now=now)
    db.commit()
    db.refresh(feedback)
    return feedback


def fingerprint(feedback: DealFeedback) -> str:
    """SHA-256 of what was said, in a fixed order, so the record proves it."""
    said = {name: getattr(feedback, name) for name in SCORES} | {"note": feedback.note}
    return record.fingerprint(json.dumps(said, sort_keys=True, separators=(",", ":")))


# --- what a profile shows ---------------------------------------------------------


def _shown(now: datetime) -> ColumnElement[bool]:
    """`feedback_rules.revealed`, asked in SQL of each answer."""
    other = aliased(DealFeedback)
    return or_(
        DealFeedback.window_ends_at <= now,
        exists().where(
            other.deal_memo_id == DealFeedback.deal_memo_id,
            other.author_side != DealFeedback.author_side,
        ),
    )


def _about(about: str, subject_id: uuid.UUID) -> Select[DealFeedback]:
    """Answers about one creator (written by brands) or one brand (by creators)."""
    query = (
        select(DealFeedback)
        .join(DealMemo, DealMemo.id == DealFeedback.deal_memo_id)
        .join(Application, Application.id == DealMemo.application_id)
        .join(Campaign, Campaign.id == Application.campaign_id)
        .where(DealFeedback.author_side == OTHER[about])
    )
    if about == "creator":
        return query.where(Application.creator_id == subject_id)
    return query.where(Campaign.brand_id == subject_id)


def figures(db: Session, about: str, subject_id: uuid.UUID, now: datetime) -> Figures:
    """Averages of the revealed answers about someone, in one query."""
    answers = _about(about, subject_id).where(_shown(now)).subquery()
    partner = answers.c.deal_memo_id
    row = db.execute(
        select(
            func.count(),
            func.avg(answers.c.brief),
            func.avg(answers.c.reliability),
            func.avg(answers.c.easy),
        ).select_from(answers)
    ).one()
    partners = db.scalar(
        select(
            func.count(
                func.distinct(
                    Campaign.brand_id if about == "creator" else Application.creator_id
                )
            )
        )
        .select_from(DealMemo)
        .join(Application, Application.id == DealMemo.application_id)
        .join(Campaign, Campaign.id == Application.campaign_id)
        .where(DealMemo.id.in_(select(partner)))
    )
    count = int(row[0])

    def average(value: Decimal | None) -> float | None:
        # Below the floor, not enough to say: null, never zero (D-038).
        if count < MIN_ANSWERS or value is None:
            return None
        return round(float(value), 2)

    return Figures(
        answers=count,
        counterparties=int(partners or 0),
        brief=average(row[1]),
        reliability=average(row[2]),
        easy=average(row[3]),
    )


def notes(
    db: Session,
    about: str,
    subject_id: uuid.UUID,
    now: datetime,
    *,
    limit: int,
    cursor: str | None,
) -> Slice[NoteAbout]:
    """Revealed notes about someone, newest first, each with their reply. Two queries."""
    query = _about(about, subject_id).where(_shown(now), DealFeedback.note.is_not(None))
    if cursor is not None:
        query = query.where(
            older_than_cursor(DealFeedback.created_at, DealFeedback.id, cursor)
        )
    rows = list(
        db.scalars(
            query.order_by(DealFeedback.created_at.desc(), DealFeedback.id.desc()).limit(
                limit + 1
            )
        ).all()
    )
    page = build_slice(rows, limit, key=lambda f: (f.created_at, f.id))
    replies = (
        {
            f.deal_memo_id: f.note
            for f in db.scalars(
                select(DealFeedback).where(
                    DealFeedback.deal_memo_id.in_([f.deal_memo_id for f in page.rows]),
                    DealFeedback.author_side == about,
                )
            )
        }
        if page.rows
        else {}
    )
    return Slice(
        rows=[NoteAbout(f, replies.get(f.deal_memo_id)) for f in page.rows],
        next_cursor=page.next_cursor,
    )


# --- the export ----------------------------------------------------------------


def export_for_account(
    db: Session, account_id: uuid.UUID, now: datetime
) -> list[ExportedSection]:
    """Feedback on this account's deals: its own, and the other side's once revealed.

    Two queries: the deals and which side the account is on, then the answers
    with whether each is revealed, asked in SQL.
    """
    from app.modules.auth.models.brand import Brand

    memo_ids = [
        m.id for m in memos_for_account(db, account_id, limit=MAX_ROWS_PER_SECTION + 1)
    ]
    rows: list[DealFeedback] = []
    if memo_ids:
        brand_side = {
            memo_id: brand_account == account_id
            for memo_id, brand_account in db.execute(
                select(DealMemo.id, Brand.account_id)
                .join(Application, Application.id == DealMemo.application_id)
                .join(Campaign, Campaign.id == Application.campaign_id)
                .join(Brand, Brand.id == Campaign.brand_id)
                .where(DealMemo.id.in_(memo_ids))
            )
        }
        for feedback, shown in db.execute(
            select(DealFeedback, _shown(now))
            .where(DealFeedback.deal_memo_id.in_(memo_ids))
            .order_by(DealFeedback.created_at, DealFeedback.id)
        ):
            mine = (feedback.author_side == "brand") == brand_side[feedback.deal_memo_id]
            if mine or shown:
                rows.append(feedback)
    return [
        build_section(
            "deal_feedback",
            table="deal_feedback",
            purpose=(
                "Feedback on your finished deals: what you said, and what the other "
                "side said once both of you had answered or the 14 days had passed."
            ),
            objects=rows,
            fields=EXPORT_FIELDS,
        )
    ]
